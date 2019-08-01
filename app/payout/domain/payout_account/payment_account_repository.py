from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from gino import Gino, GinoConnection

from app.commons.utils.dataclass_extensions import no_init_field
from app.payout.repository.maindb.model.payment_account import PaymentAccountTable
from app.payout.domain.payout_account.models import PayoutAccount


@dataclass
class PayoutAccountRepository:
    _gino: Gino
    _table: PaymentAccountTable = no_init_field()

    def __post_init__(self):
        self._table = PaymentAccountTable(self._gino)

    async def get_payout_account_by_id(
        self, payment_account_id: int
    ) -> Optional[PayoutAccount]:
        stmt = self._table.table.select().where(self._table.id == payment_account_id)
        async with self._gino.acquire() as connection:  # type: GinoConnection
            row = await connection.first(stmt)

        return self._deserialize_to_payout_account(row) if row else None

    async def create_payout_account(self, to_create: PayoutAccount) -> PayoutAccount:
        data = {
            self._table.resolve_outstanding_balance_frequency: to_create.resolve_outstanding_balance_frequency,
            self._table.payout_disabled: to_create.payout_disabled,
            self._table.statement_descriptor: to_create.statement_descriptor,
            self._table.charges_enabled: to_create.charges_enabled,
            self._table.transfers_enabled: to_create.transfers_enabled,
            self._table.is_verified_with_stripe: to_create.is_verified_with_stripe,
            self._table.upgraded_to_managed_account_at: to_create.upgraded_to_managed_account_at,
            self._table.old_account_id: to_create.old_account_id,
            self._table.entity: to_create.entity,
            self._table.account_type: to_create.account_type,
            self._table.account_id: to_create.account_id,
        }

        stmt = (
            self._table.table.insert()
            .values(data)
            .returning(*self._table.table.columns.values())
        )

        async with self._gino.acquire() as connection:  # type: GinoConnection
            row = await connection.first(stmt)

        return self._deserialize_to_payout_account(row)

    def _deserialize_to_payout_account(self, row: Any) -> PayoutAccount:
        return PayoutAccount(
            id=row[self._table.id],
            account_id=row[self._table.account_id],
            account_type=row[self._table.account_type],
            entity=row[self._table.entity],
            old_account_id=row[self._table.old_account_id],
            upgraded_to_managed_account_at=row[
                self._table.upgraded_to_managed_account_at
            ],
            is_verified_with_stripe=row[self._table.is_verified_with_stripe],
            transfers_enabled=row[self._table.transfers_enabled],
            charges_enabled=row[self._table.charges_enabled],
            statement_descriptor=row[self._table.statement_descriptor],
            created_at=row[self._table.created_at],
            payout_disabled=row[self._table.payout_disabled],
            resolve_outstanding_balance_frequency=row[
                self._table.resolve_outstanding_balance_frequency
            ],
        )