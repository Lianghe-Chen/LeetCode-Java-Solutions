from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel
from typing_extensions import final
from app.payin.core.cart_payment.types import CartType, IntentStatus, ChargeStatus
from uuid import UUID


@final
class LegacyPayment(BaseModel):
    dd_consumer_id: Optional[str] = None
    dd_stripe_card_id: Optional[str] = None
    dd_charge_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_payment_method_id: Optional[str] = None
    stripe_card_id: Optional[str] = None


@final
class SplitPayment(BaseModel):
    payout_account_id: str
    application_fee_amount: int


@final
class CartMetadata(BaseModel):
    reference_id: int
    ct_reference_id: int
    type: CartType


class CartPayment(BaseModel):
    id: UUID
    amount: int
    payer_id: str
    payment_method_id: Optional[str]
    delay_capture: bool
    cart_metadata: CartMetadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    client_description: Optional[str] = None
    payer_statement_description: Optional[str] = None
    legacy_payment: Optional[LegacyPayment] = None
    split_payment: Optional[SplitPayment] = None
    capture_after: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


@final
class PaymentIntent(BaseModel):
    id: UUID
    cart_payment_id: UUID
    idempotency_key: str
    amount_initiated: int
    amount: int
    amount_capturable: Optional[int]  # TODO fix use of this field
    amount_received: Optional[int]
    application_fee_amount: Optional[int]
    capture_method: str
    confirmation_method: str
    country: str
    currency: str
    status: IntentStatus
    statement_descriptor: Optional[str]
    created_at: datetime
    updated_at: datetime
    captured_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    capture_after: Optional[datetime]


@final
@dataclass(frozen=True)
class PgpPaymentIntent:
    id: UUID
    payment_intent_id: UUID
    idempotency_key: str
    provider: str
    resource_id: Optional[str]
    status: IntentStatus
    invoice_resource_id: Optional[str]
    charge_resource_id: Optional[str]
    payment_method_resource_id: str
    currency: str
    amount: int
    amount_capturable: Optional[int]
    amount_received: Optional[int]
    application_fee_amount: Optional[int]
    payout_account_id: Optional[str]
    capture_method: str
    confirmation_method: str
    created_at: datetime
    updated_at: datetime
    captured_at: Optional[datetime]
    cancelled_at: Optional[datetime]


@final
@dataclass(frozen=True)
class PaymentIntentAdjustmentHistory:
    id: UUID
    payer_id: str
    payment_intent_id: UUID
    amount: int
    amount_original: int
    amount_delta: int
    currency: str
    created_at: datetime


@final
@dataclass(frozen=True)
class PaymentCharge:
    id: UUID
    payment_intent_id: UUID
    provider: str
    idempotency_key: str
    status: ChargeStatus
    currency: str
    amount: int
    amount_refunded: int
    application_fee_amount: Optional[int]
    payout_account_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    captured_at: Optional[datetime]
    cancelled_at: Optional[datetime]


@final
@dataclass(frozen=True)
class PgpPaymentCharge:
    id: UUID
    payment_charge_id: UUID
    provider: str
    idempotency_key: str
    status: ChargeStatus
    currency: str
    amount: int
    amount_refunded: int
    application_fee_amount: Optional[int]
    payout_account_id: Optional[str]
    resource_id: Optional[str]
    intent_resource_id: Optional[str]
    invoice_resource_id: Optional[str]
    payment_method_resource_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    captured_at: Optional[datetime]
    cancelled_at: Optional[datetime]
