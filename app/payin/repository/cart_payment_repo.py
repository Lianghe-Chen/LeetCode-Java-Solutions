from dataclasses import dataclass
from typing import Any, List, Optional
from uuid import UUID

from typing_extensions import final

from app.payin.core.cart_payment.model import (
    CartPayment,
    CartMetadata,
    PaymentIntent,
    PgpPaymentIntent,
    PaymentIntentAdjustmentHistory,
    PaymentCharge,
    PgpPaymentCharge,
)
from app.payin.core.cart_payment.types import IntentStatus, ChargeStatus
from app.payin.models.paymentdb import (
    cart_payments,
    payment_intents,
    pgp_payment_intents,
    payment_intents_adjustment_history,
    payment_charges,
    pgp_payment_charges,
)
from app.payin.repository.base import PayinDBRepository


@final
@dataclass
class CartPaymentRepository(PayinDBRepository):
    async def insert_cart_payment(
        self,
        *,
        id: UUID,
        payer_id: str,
        type: str,
        client_description: Optional[str],
        reference_id: int,
        reference_ct_id: int,
        legacy_consumer_id: Optional[int],
        amount_original: int,
        amount_total: int,
    ) -> CartPayment:
        data = {
            cart_payments.id: id,
            cart_payments.payer_id: payer_id,
            cart_payments.type: type,
            cart_payments.client_description: client_description,
            cart_payments.reference_id: reference_id,
            cart_payments.reference_ct_id: reference_ct_id,
            cart_payments.legacy_consumer_id: legacy_consumer_id,
            cart_payments.amount_original: amount_original,
            cart_payments.amount_total: amount_total,
        }

        statement = (
            cart_payments.table.insert()
            .values(data)
            .returning(*cart_payments.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_cart_payment(row)

    def to_cart_payment(self, row: Any) -> CartPayment:
        return CartPayment(
            id=row[cart_payments.id],
            payer_id=row[cart_payments.payer_id],
            amount=row[cart_payments.amount_total],
            capture_method=None,
            payment_method_id=None,
            client_description=row[cart_payments.client_description],
            cart_metadata=CartMetadata(
                reference_id=row[cart_payments.reference_id],
                ct_reference_id=row[cart_payments.reference_ct_id],
                type=row[cart_payments.type],
            ),
            created_at=row[cart_payments.created_at],
            updated_at=row[cart_payments.updated_at],
        )

    async def find_uncaptured_payment_intents(self) -> List[PaymentIntent]:
        statement = payment_intents.table.select().where(
            payment_intents.status == IntentStatus.REQUIRES_CAPTURE
        )
        results = await self.payment_database.master().fetch_all(statement)
        return [self.to_payment_intent(row) for row in results]

    async def get_cart_payment_by_id(self, cart_payment_id: UUID) -> CartPayment:
        statement = cart_payments.table.select().where(
            cart_payments.id == cart_payment_id
        )
        row = await self.payment_database.master().fetch_one(statement)

        return self.to_cart_payment(row)

    async def update_cart_payment_details(
        self, cart_payment_id: UUID, amount: int, client_description: Optional[str]
    ) -> CartPayment:
        statement = (
            cart_payments.table.update()
            .where(cart_payments.id == cart_payment_id)
            .values(amount_total=amount, client_description=client_description)
            .returning(*cart_payments.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_cart_payment(row)

    async def insert_payment_intent(
        self,
        id: UUID,
        cart_payment_id: UUID,
        idempotency_key: str,
        amount_initiated: int,
        amount: int,
        application_fee_amount: Optional[int],
        country: str,
        currency: str,
        capture_method: str,
        confirmation_method: str,
        status: str,
        statement_descriptor: Optional[str],
    ) -> PaymentIntent:
        data = {
            payment_intents.id: id,
            payment_intents.cart_payment_id: cart_payment_id,
            payment_intents.idempotency_key: idempotency_key,
            payment_intents.amount_initiated: amount_initiated,
            payment_intents.amount: amount,
            payment_intents.application_fee_amount: application_fee_amount,
            payment_intents.country: country,
            payment_intents.currency: currency,
            payment_intents.capture_method: capture_method,
            payment_intents.confirmation_method: confirmation_method,
            payment_intents.status: status,
            payment_intents.statement_descriptor: statement_descriptor,
        }

        statement = (
            payment_intents.table.insert()
            .values(data)
            .returning(*payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_intent(row)

    def to_payment_intent(self, row: Any) -> PaymentIntent:
        return PaymentIntent(
            id=row[payment_intents.id],
            cart_payment_id=row[payment_intents.cart_payment_id],
            idempotency_key=row[payment_intents.idempotency_key],
            amount_initiated=row[payment_intents.amount_initiated],
            amount=row[payment_intents.amount],
            amount_capturable=row[payment_intents.amount_capturable],
            amount_received=row[payment_intents.amount_received],
            application_fee_amount=row[payment_intents.application_fee_amount],
            capture_method=row[payment_intents.capture_method],
            confirmation_method=row[payment_intents.confirmation_method],
            country=row[payment_intents.country],
            currency=row[payment_intents.currency],
            status=IntentStatus(row[payment_intents.status]),
            statement_descriptor=row[payment_intents.statement_descriptor],
            created_at=row[payment_intents.created_at],
            updated_at=row[payment_intents.updated_at],
            captured_at=row[payment_intents.captured_at],
            cancelled_at=row[payment_intents.cancelled_at],
        )

    async def update_payment_intent_status(
        self, id: UUID, status: str
    ) -> PaymentIntent:
        statement = (
            payment_intents.table.update()
            .where(payment_intents.id == id)
            .values(status=status)
            .returning(*payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_intent(row)

    async def update_payment_intent_amount(
        self, id: UUID, amount: int
    ) -> PaymentIntent:
        statement = (
            payment_intents.table.update()
            .where(payment_intents.id == id)
            .values(amount=amount)
            .returning(*payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_intent(row)

    async def get_payment_intent_for_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[PaymentIntent]:
        statement = payment_intents.table.select().where(
            payment_intents.idempotency_key == idempotency_key
        )
        row = await self.payment_database.master().fetch_one(statement)

        if not row:
            return None

        return self.to_payment_intent(row)

    async def get_payment_intents_for_cart_payment(
        self, cart_payment_id: UUID
    ) -> List[PaymentIntent]:
        statement = payment_intents.table.select().where(
            payment_intents.cart_payment_id == cart_payment_id
        )
        results = await self.payment_database.master().fetch_all(statement)

        return [self.to_payment_intent(row) for row in results]

    async def insert_pgp_payment_intent(
        self,
        id: UUID,
        payment_intent_id: UUID,
        idempotency_key: str,
        provider: str,
        payment_method_resource_id: str,
        currency: str,
        amount: int,
        application_fee_amount: Optional[int],
        payout_account_id: Optional[str],
        capture_method: str,
        confirmation_method: str,
        status: str,
        statement_descriptor: Optional[str],
    ) -> PgpPaymentIntent:
        data = {
            pgp_payment_intents.id: id,
            pgp_payment_intents.payment_intent_id: payment_intent_id,
            pgp_payment_intents.idempotency_key: idempotency_key,
            pgp_payment_intents.provider: provider,
            pgp_payment_intents.payment_method_resource_id: payment_method_resource_id,
            pgp_payment_intents.currency: currency,
            pgp_payment_intents.amount: amount,
            pgp_payment_intents.application_fee_amount: application_fee_amount,
            pgp_payment_intents.payout_account_id: payout_account_id,
            pgp_payment_intents.capture_method: capture_method,
            pgp_payment_intents.confirmation_method: confirmation_method,
            pgp_payment_intents.status: status,
            pgp_payment_intents.statement_descriptor: statement_descriptor,
        }

        statement = (
            pgp_payment_intents.table.insert()
            .values(data)
            .returning(*pgp_payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_intent(row)

    async def update_pgp_payment_intent(
        self, id: UUID, status: str, resource_id: str, charge_resource_id: str
    ) -> PgpPaymentIntent:
        statement = (
            pgp_payment_intents.table.update()
            .where(pgp_payment_intents.id == id)
            .values(
                status=status,
                resource_id=resource_id,
                charge_resource_id=charge_resource_id,
            )
            .returning(*pgp_payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_intent(row)

    async def update_pgp_payment_intent_status(
        self, id: UUID, status: str
    ) -> PgpPaymentIntent:
        statement = (
            pgp_payment_intents.table.update()
            .where(pgp_payment_intents.id == id)
            .values(status=status)
            .returning(*pgp_payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_intent(row)

    async def update_pgp_payment_intent_amount(
        self, id: UUID, amount: int
    ) -> PgpPaymentIntent:
        statement = (
            pgp_payment_intents.table.update()
            .where(pgp_payment_intents.id == id)
            .values(amount=amount)
            .returning(*pgp_payment_intents.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_intent(row)

    async def find_pgp_payment_intents(
        self, payment_intent_id: UUID
    ) -> List[PgpPaymentIntent]:
        statement = (
            pgp_payment_intents.table.select()
            .where(pgp_payment_intents.payment_intent_id == payment_intent_id)
            .order_by(pgp_payment_intents.created_at.asc())
        )
        query_results = await self.payment_database.master().fetch_all(statement)

        matched_intents = []
        for row in query_results:
            matched_intents.append(self.to_pgp_payment_intent(row))
        return matched_intents

    def to_pgp_payment_intent(self, row: Any) -> PgpPaymentIntent:
        return PgpPaymentIntent(
            id=row[pgp_payment_intents.id],
            payment_intent_id=row[pgp_payment_intents.payment_intent_id],
            idempotency_key=row[pgp_payment_intents.idempotency_key],
            provider=row[pgp_payment_intents.provider],
            resource_id=row[pgp_payment_intents.resource_id],
            status=IntentStatus(row[pgp_payment_intents.status]),
            invoice_resource_id=row[pgp_payment_intents.invoice_resource_id],
            charge_resource_id=row[pgp_payment_intents.charge_resource_id],
            payment_method_resource_id=row[
                pgp_payment_intents.payment_method_resource_id
            ],
            currency=row[pgp_payment_intents.currency],
            amount=row[pgp_payment_intents.amount],
            amount_capturable=row[pgp_payment_intents.amount_capturable],
            amount_received=row[pgp_payment_intents.amount_received],
            application_fee_amount=row[pgp_payment_intents.application_fee_amount],
            capture_method=row[pgp_payment_intents.capture_method],
            confirmation_method=row[pgp_payment_intents.confirmation_method],
            payout_account_id=row[pgp_payment_intents.payout_account_id],
            created_at=row[pgp_payment_intents.created_at],
            updated_at=row[pgp_payment_intents.updated_at],
            captured_at=row[pgp_payment_intents.captured_at],
            cancelled_at=row[pgp_payment_intents.cancelled_at],
        )

    async def insert_payment_intent_adjustment_history(
        self,
        id: UUID,
        payer_id: str,
        payment_intent_id: UUID,
        amount: int,
        amount_original: int,
        amount_delta: int,
        currency: str,
    ) -> PaymentIntentAdjustmentHistory:
        data = {
            payment_intents_adjustment_history.id: id,
            payment_intents_adjustment_history.payer_id: payer_id,
            payment_intents_adjustment_history.payment_intent_id: payment_intent_id,
            payment_intents_adjustment_history.amount: amount,
            payment_intents_adjustment_history.amount_original: amount_original,
            payment_intents_adjustment_history.amount_delta: amount_delta,
            payment_intents_adjustment_history.currency: currency,
        }

        statement = (
            payment_intents_adjustment_history.table.insert()
            .values(data)
            .returning(*payment_intents_adjustment_history.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_intent_adjustment_history(row)

    def to_payment_intent_adjustment_history(
        self, row: Any
    ) -> PaymentIntentAdjustmentHistory:
        return PaymentIntentAdjustmentHistory(
            id=row[payment_intents_adjustment_history.id],
            payer_id=row[payment_intents_adjustment_history.payer_id],
            payment_intent_id=row[payment_intents_adjustment_history.payment_intent_id],
            amount=row[payment_intents_adjustment_history.amount],
            amount_original=row[payment_intents_adjustment_history.amount_original],
            amount_delta=row[payment_intents_adjustment_history.amount_delta],
            currency=row[payment_intents_adjustment_history.currency],
            created_at=row[payment_intents_adjustment_history.created_at],
        )

    async def insert_payment_charge(
        self,
        id: UUID,
        payment_intent_id: UUID,
        provider: str,
        idempotency_key: str,
        status: str,
        currency: str,
        amount: int,
        amount_refunded: int,
        application_fee_amount: Optional[int],
        payout_account_id: Optional[str],
    ) -> PaymentCharge:
        data = {
            payment_charges.id: str(id),
            payment_charges.payment_intent_id: str(payment_intent_id),
            payment_charges.provider: provider,
            payment_charges.idempotency_key: idempotency_key,
            payment_charges.status: status,
            payment_charges.currency: currency,
            payment_charges.amount: amount,
            payment_charges.amount_refunded: amount_refunded,
            payment_charges.application_fee_amount: application_fee_amount,
            payment_charges.payout_account_id: payout_account_id,
        }

        statement = (
            payment_charges.table.insert()
            .values(data)
            .returning(*payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_charge(row)

    def to_payment_charge(self, row: Any) -> PaymentCharge:
        return PaymentCharge(
            id=row[payment_charges.id],
            payment_intent_id=row[payment_charges.payment_intent_id],
            provider=row[payment_charges.provider],
            idempotency_key=row[payment_charges.idempotency_key],
            status=ChargeStatus(row[payment_charges.status]),
            currency=row[payment_charges.currency],
            amount=row[payment_charges.amount],
            amount_refunded=row[payment_charges.amount_refunded],
            application_fee_amount=row[payment_charges.application_fee_amount],
            payout_account_id=row[payment_charges.payout_account_id],
            created_at=row[payment_charges.created_at],
            updated_at=row[payment_charges.updated_at],
            captured_at=row[payment_charges.captured_at],
            cancelled_at=row[payment_charges.cancelled_at],
        )

    async def update_payment_charge_status(
        self, payment_intent_id: UUID, status: str
    ) -> PaymentCharge:
        # We expect a 1-1 relationship between intent and charge for our use cases.
        # As an optimization, support updating based on intent_id, which avoids an extra
        # round trip to fetch the record to update.
        statement = (
            payment_charges.table.update()
            .where(payment_charges.payment_intent_id == payment_intent_id)
            .values(status=status)
            .returning(*payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_charge(row)

    async def update_payment_charge(
        self, payment_intent_id: UUID, status: str, amount_refunded: int
    ) -> PaymentCharge:
        statement = (
            payment_charges.table.update()
            .where(payment_charges.payment_intent_id == payment_intent_id)
            .values(status=status, amount_refunded=amount_refunded)
            .returning(*payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_charge(row)

    async def update_payment_charge_amount(
        self, payment_intent_id: UUID, amount: int
    ) -> PaymentCharge:
        statement = (
            payment_charges.table.update()
            .where(payment_charges.payment_intent_id == payment_intent_id)
            .values(amount=amount)
            .returning(*payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_payment_charge(row)

    async def insert_pgp_payment_charge(
        self,
        id: UUID,
        payment_charge_id: UUID,
        provider: str,
        idempotency_key: str,
        status: str,
        currency: str,
        amount: int,
        amount_refunded: int,
        application_fee_amount: Optional[int],
        payout_account_id: Optional[str],
        resource_id: Optional[str],
        intent_resource_id: Optional[str],
        invoice_resource_id: Optional[str],
        payment_method_resource_id: Optional[str],
    ) -> PgpPaymentCharge:
        data = {
            pgp_payment_charges.id: id,
            pgp_payment_charges.payment_charge_id: payment_charge_id,
            pgp_payment_charges.provider: provider,
            pgp_payment_charges.idempotency_key: idempotency_key,
            pgp_payment_charges.status: status,
            pgp_payment_charges.currency: currency,
            pgp_payment_charges.amount: amount,
            pgp_payment_charges.amount_refunded: amount_refunded,
            pgp_payment_charges.application_fee_amount: application_fee_amount,
            pgp_payment_charges.payout_account_id: payout_account_id,
            pgp_payment_charges.resource_id: resource_id,
            pgp_payment_charges.intent_resource_id: intent_resource_id,
            pgp_payment_charges.invoice_resource_id: invoice_resource_id,
            pgp_payment_charges.payment_method_resource_id: payment_method_resource_id,
        }

        statement = (
            pgp_payment_charges.table.insert()
            .values(data)
            .returning(*pgp_payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_charge(row)

    def to_pgp_payment_charge(self, row: Any) -> PgpPaymentCharge:
        return PgpPaymentCharge(
            id=row[pgp_payment_charges.id],
            payment_charge_id=row[pgp_payment_charges.payment_charge_id],
            provider=row[pgp_payment_charges.provider],
            idempotency_key=row[pgp_payment_charges.idempotency_key],
            status=ChargeStatus(row[pgp_payment_charges.status]),
            currency=row[pgp_payment_charges.currency],
            amount=row[pgp_payment_charges.amount],
            amount_refunded=row[pgp_payment_charges.amount_refunded],
            application_fee_amount=row[pgp_payment_charges.application_fee_amount],
            payout_account_id=row[pgp_payment_charges.payout_account_id],
            resource_id=row[pgp_payment_charges.resource_id],
            intent_resource_id=row[pgp_payment_charges.intent_resource_id],
            invoice_resource_id=row[pgp_payment_charges.invoice_resource_id],
            payment_method_resource_id=row[
                pgp_payment_charges.payment_method_resource_id
            ],
            created_at=row[pgp_payment_charges.created_at],
            updated_at=row[pgp_payment_charges.updated_at],
            captured_at=row[pgp_payment_charges.captured_at],
            cancelled_at=row[pgp_payment_charges.cancelled_at],
        )

    async def update_pgp_payment_charge(
        self, payment_charge_id: UUID, status: str, amount: int, amount_refunded: int
    ) -> PgpPaymentCharge:
        # We expect a 1-1 relationship between charge and pgp_charge for our use cases.
        # As an optimization, support updating based on charge_id, which avoids an extra
        # round trip to fetch the record to update.
        statement = (
            pgp_payment_charges.table.update()
            .where(pgp_payment_charges.payment_charge_id == str(payment_charge_id))
            .values(status=status, amount=amount, amount_refunded=amount_refunded)
            .returning(*pgp_payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_charge(row)

    async def update_pgp_payment_charge_amount(
        self, payment_charge_id: UUID, amount: int
    ) -> PgpPaymentCharge:
        statement = (
            pgp_payment_charges.table.update()
            .where(pgp_payment_charges.payment_charge_id == str(payment_charge_id))
            .values(amount=amount)
            .returning(*pgp_payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_charge(row)

    async def update_pgp_payment_charge_status(
        self, payment_charge_id: UUID, status: str
    ) -> PgpPaymentCharge:
        statement = (
            pgp_payment_charges.table.update()
            .where(pgp_payment_charges.payment_charge_id == payment_charge_id)
            .values(status=status)
            .returning(*pgp_payment_charges.table.columns.values())
        )

        row = await self.payment_database.master().fetch_one(statement)
        return self.to_pgp_payment_charge(row)