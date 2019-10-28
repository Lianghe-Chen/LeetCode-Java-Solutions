from datetime import datetime, timedelta

from starlette.status import HTTP_400_BAD_REQUEST

from app.commons.api.models import DEFAULT_INTERNAL_EXCEPTION, PaymentException
from structlog.stdlib import BoundLogger
from typing import Union, Optional, List, Tuple
from app.commons.core.processor import (
    AsyncOperation,
    OperationRequest,
    OperationResponse,
)
from app.payout.constants import (
    FRAUD_ENABLE_MX_PAYOUT_DELAY_AFTER_BANK_CHANGE,
    FRAUD_BUSINESS_WHITELIST_FOR_PAYOUT_DELAY_AFTER_BANK_CHANGE,
    FRAUD_MINIMUM_HOURS_BEFORE_MX_PAYOUT_AFTER_BANK_CHANGE,
    DISABLE_DASHER_PAYMENT_ACCOUNT_LIST_NAME,
    DISABLE_MERCHANT_PAYMENT_ACCOUNT_LIST_NAME,
)
from app.payout.core.account.utils import (
    get_country_shortname,
    COUNTRY_TO_CURRENCY_CODE,
)
from app.payout.core.transfer.utils import (
    determine_transfer_status_from_latest_submission,
)
from app.payout.repository.bankdb.model.transaction import (
    TransactionDBEntity,
    TransactionUpdateDBEntity,
)
from app.payout.repository.bankdb.payment_account_edit_history import (
    PaymentAccountEditHistoryRepositoryInterface,
)
from app.payout.repository.bankdb.transaction import TransactionRepositoryInterface
from app.payout.repository.maindb.model.payment_account import PaymentAccount
from app.payout.repository.maindb.model.transfer import (
    Transfer,
    TransferCreate,
    TransferUpdate,
    TransferStatus,
)
from app.payout.repository.maindb.payment_account import (
    PaymentAccountRepositoryInterface,
)
from app.payout.repository.maindb.stripe_transfer import (
    StripeTransferRepositoryInterface,
)
from app.payout.repository.maindb.transfer import TransferRepositoryInterface
import app.payout.models as payout_models
from app.payout.core.exceptions import PayoutError, PayoutErrorCode
from app.commons.runtime import runtime


class CreateTransferResponse(OperationResponse):
    transfer: Optional[Transfer]
    transaction_ids: List[int]


class CreateTransferRequest(OperationRequest):
    payout_account_id: int
    transfer_type: str
    bank_info_recently_changed: bool
    end_time: datetime
    start_time: Optional[datetime]
    target_id: Optional[int]
    target_type: Optional[payout_models.PayoutTargetType]
    target_business_id: Optional[int]
    payout_countries: Optional[List[str]]


class CreateTransfer(AsyncOperation[CreateTransferRequest, CreateTransferResponse]):
    """
    Processor to create a transfer. This is used for both weekly and manually create_transfer
    """

    transfer_repo: TransferRepositoryInterface
    payment_account_repo: PaymentAccountRepositoryInterface
    payment_account_edit_history_repo: PaymentAccountEditHistoryRepositoryInterface
    transaction_repo: TransactionRepositoryInterface
    stripe_transfer_repo: StripeTransferRepositoryInterface

    def __init__(
        self,
        request: CreateTransferRequest,
        *,
        transfer_repo: TransferRepositoryInterface,
        payment_account_repo: PaymentAccountRepositoryInterface,
        payment_account_edit_history_repo: PaymentAccountEditHistoryRepositoryInterface,
        transaction_repo: TransactionRepositoryInterface,
        stripe_transfer_repo: StripeTransferRepositoryInterface,
        logger: BoundLogger = None,
    ):
        super().__init__(request, logger)
        self.request = request
        self.transfer_repo = transfer_repo
        self.payment_account_repo = payment_account_repo
        self.payment_account_edit_history_repo = payment_account_edit_history_repo
        self.transaction_repo = transaction_repo
        self.stripe_transfer_repo = stripe_transfer_repo

    async def _execute(self) -> CreateTransferResponse:
        self.logger.info(
            "Creating transfer for account.",
            payment_account_id=self.request.payout_account_id,
        )
        payment_account = await self.payment_account_repo.get_payment_account_by_id(
            payment_account_id=self.request.payout_account_id
        )
        # payment_account should always be valid
        if not payment_account:
            raise PayoutError(
                http_status_code=HTTP_400_BAD_REQUEST,
                error_code=PayoutErrorCode.INVALID_PAYMENT_ACCOUNT_ID,
                retryable=False,
            )
        # logic within following if statement is from create_transfer_for_account_id
        # when a transfer creation is triggered manually, we do not need to execute following logic
        if self.request.transfer_type != payout_models.TransferType.MANUAL:
            if self.request.payout_countries:
                stripe_managed_account = (
                    await self.payment_account_repo.get_stripe_managed_account_by_id(
                        payment_account.account_id
                    )
                    if payment_account.account_id
                    else None
                )
                if (
                    stripe_managed_account
                    and stripe_managed_account.country_shortname
                    not in self.request.payout_countries
                ):
                    self.logger.debug(
                        "Skipping transfer for account because the payout country does not match",
                        payment_account_id=payment_account.id,
                        account_country=stripe_managed_account.country_shortname,
                        payout_countries=self.request.payout_countries,
                    )
                    return CreateTransferResponse(transfer=None, transaction_ids=[])
            if not await self.should_payment_account_be_auto_paid_weekly(
                payment_account_id=payment_account.id,
                target_type=self.request.target_type,
                target_id=self.request.target_id,
                target_biz_id=self.request.target_business_id,
            ):
                self.logger.info(
                    "Payment stopped: Ignoring creating weekly transfer for account id",
                    payment_account_id=payment_account.id,
                )
                return CreateTransferResponse(transfer=None, transaction_ids=[])

        currency = await self._get_currency(payment_account=payment_account)
        transfer, transaction_ids = await self.create_transfer_for_unpaid_transactions(
            payment_account_id=payment_account.id,
            currency=currency,
            start_time=self.request.start_time,
            end_time=self.request.end_time,
        )
        return CreateTransferResponse(
            transfer=transfer, transaction_ids=transaction_ids
        )

    def _handle_exception(
        self, dep_exec: BaseException
    ) -> Union[PaymentException, CreateTransferResponse]:
        raise DEFAULT_INTERNAL_EXCEPTION

    async def should_payment_account_be_auto_paid_weekly(
        self,
        payment_account_id: int,
        target_type: Optional[payout_models.PayoutTargetType],
        target_id: Optional[int],
        target_biz_id: Optional[int],
    ) -> bool:
        #  Check for potential mx banking fraud
        if await self.should_block_mx_payout(
            payment_account_id=payment_account_id,
            payout_date_time=datetime.utcnow(),
            target_type=target_type,
            target_id=target_id,
            target_biz_id=target_biz_id,
        ):
            return False

        #  Check for manually set payment stop
        dasher_payment_account_stop_list = runtime.get_json(
            DISABLE_DASHER_PAYMENT_ACCOUNT_LIST_NAME, []
        )
        merchant_payment_account_stop_list = runtime.get_json(
            DISABLE_MERCHANT_PAYMENT_ACCOUNT_LIST_NAME, []
        )
        account_stop_list = (
            dasher_payment_account_stop_list + merchant_payment_account_stop_list
        )
        return payment_account_id not in account_stop_list

    async def should_block_mx_payout(
        self,
        payout_date_time: datetime,
        payment_account_id: int,
        target_type: Optional[payout_models.PayoutTargetType],
        target_id: Optional[int],
        target_biz_id: Optional[int],
    ) -> bool:
        # todo: copy existing nimda variables and runtime flags into PS
        if runtime.get_bool(FRAUD_ENABLE_MX_PAYOUT_DELAY_AFTER_BANK_CHANGE, False):
            try:
                if (
                    target_type == payout_models.PayoutTargetType.STORE
                    and target_biz_id
                    not in runtime.get_json(
                        FRAUD_BUSINESS_WHITELIST_FOR_PAYOUT_DELAY_AFTER_BANK_CHANGE, []
                    )
                ):
                    time_window_to_check_in_hours = runtime.get_int(
                        FRAUD_MINIMUM_HOURS_BEFORE_MX_PAYOUT_AFTER_BANK_CHANGE, 0
                    )
                    if time_window_to_check_in_hours == 0:
                        return False
                    recent_bank_change_threshold = payout_date_time - timedelta(
                        hours=time_window_to_check_in_hours
                    )
                    bank_info_recently_changed = await self.payment_account_edit_history_repo.get_bank_updates_for_store_with_payment_account_and_time_range(
                        payment_account_id=payment_account_id,
                        start_time=recent_bank_change_threshold,
                        end_time=payout_date_time,
                    )
                    if len(bank_info_recently_changed) > 0:
                        # todo: need to investigate how doorstats_global.incr and segment_merchant.track work
                        return True
            except Exception as e:
                self.logger.exception("Exception in should_block_mx_payout", error=e)
        return False

    async def _get_currency(self, payment_account: PaymentAccount) -> Optional[str]:
        country_shortname = await get_country_shortname(
            payment_account=payment_account,
            payment_account_repository=self.payment_account_repo,
        )
        if country_shortname in COUNTRY_TO_CURRENCY_CODE:
            return COUNTRY_TO_CURRENCY_CODE[country_shortname]

        return None

    async def create_transfer_for_unpaid_transactions(
        self,
        payment_account_id: int,
        end_time: datetime,
        currency: Optional[str],
        start_time: Optional[datetime],
    ) -> Tuple[Optional[Transfer], List[int]]:
        # todo: add payment lock after it is done
        transfer, transaction_ids = await self.create_with_redis_lock(
            payment_account_id=payment_account_id,
            currency=currency,
            start_time=start_time,
            end_time=end_time,
        )
        if not transfer or not transaction_ids:
            return None, []
        return transfer, transaction_ids

    async def create_with_redis_lock(
        self,
        payment_account_id: int,
        end_time: datetime,
        currency: Optional[str],
        start_time: Optional[datetime],
    ) -> Tuple[Optional[Transfer], List[int]]:
        # todo: add redis lock after it is done
        unpaid_transactions = await self.transaction_repo.get_unpaid_transaction_by_payout_account_id_without_limit(
            payout_account_id=payment_account_id,
            start_time=start_time,
            end_time=end_time,
        )
        if len(unpaid_transactions) <= 0:
            return None, []
        return await self.create_transfer_for_transactions(
            payment_account_id=payment_account_id,
            unpaid_transactions=unpaid_transactions,
            currency=currency,
        )

    async def create_transfer_for_transactions(
        self,
        payment_account_id: int,
        unpaid_transactions: List[TransactionDBEntity],
        currency: Optional[str],
    ) -> Tuple[Optional[Transfer], List[int]]:
        subtotal = self.compute_transfer_total_from_transactions(
            transactions=unpaid_transactions
        )
        if subtotal < 0:
            return None, []
        # Default behavior in DSJ is that for create_transfer_for_transactions, since there is no adjustments,
        # transfer.amount = transfer.subtotal. Also, method default to ""
        create_request = TransferCreate(
            payment_account_id=payment_account_id,
            subtotal=subtotal,
            amount=subtotal,
            adjustments="{}",
            method="",
            currency=currency,
            status=TransferStatus.CREATING,
        )
        transfer = await self.transfer_repo.create_transfer(data=create_request)
        transaction_ids = [transaction.id for transaction in unpaid_transactions]
        update_transaction_request = TransactionUpdateDBEntity(transfer_id=transfer.id)
        updated_transactions = await self.transaction_repo.update_transaction_ids_without_transfer_id(
            transaction_ids=transaction_ids, data=update_transaction_request
        )

        transfer_status = await determine_transfer_status_from_latest_submission(
            transfer=transfer, stripe_transfer_repo=self.stripe_transfer_repo
        )
        update_transfer_request = TransferUpdate(status=transfer_status)
        updated_transfer = await self.transfer_repo.update_transfer_by_id(
            transfer_id=transfer.id, data=update_transfer_request
        )
        assert updated_transfer, "updated transfer cannot be None"
        self.logger.info(
            "Transfer is attaching to transaction list",
            transfer_id=updated_transfer.id,
            transaction_list=[
                "tx <{}> {}".format(t.id, t.amount) for t in updated_transactions
            ],
        )

        if not (len(updated_transactions) == len(unpaid_transactions)):
            self.logger.error(
                "Inconsistency updating transactions",
                updated_transactions_count=len(updated_transactions),
                transaction_count=len(unpaid_transactions),
            )

        self.logger.info(
            "Transfer is being created with total amount and transaction_ids",
            transfer_id=updated_transfer.id,
            transaction_list=[
                "tx <{}> {}".format(t.id, t.amount) for t in updated_transactions
            ],
        )
        return updated_transfer, [t.id for t in updated_transactions]

    def compute_transfer_total_from_transactions(
        self, transactions: List[TransactionDBEntity]
    ) -> int:
        """
        Computes the transfer total from the transactions passed
        :param transactions:
        :return: transfer amount
        """
        amount = sum(t.amount for t in transactions)
        return amount
