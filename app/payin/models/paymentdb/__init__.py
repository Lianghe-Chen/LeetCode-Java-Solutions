import sqlalchemy

from app.payin.models.paymentdb.payer import PayerTable
from app.payin.models.paymentdb.pgp_customer import PgpCustomerTable
from app.payin.models.paymentdb.cart_payment import CartPaymentTable
from app.payin.models.paymentdb.payment_intent import PaymentIntentTable
from app.payin.models.paymentdb.pgp_payment_intent import PgpPaymentIntentTable
from app.payin.models.paymentdb.pgp_payment_method import PgpPaymentMethodTable
from app.payin.models.paymentdb.payment_intent_adjustment_history import (
    PaymentIntentAdjustmentTable,
)
from app.payin.models.paymentdb.payment_charge import PaymentChargeTable
from app.payin.models.paymentdb.pgp_payment_charge import PgpPaymentChargeTable

payin_paymentdb_metadata = sqlalchemy.MetaData()

payers = PayerTable(db_metadata=payin_paymentdb_metadata)
pgp_customers = PgpCustomerTable(db_metadata=payin_paymentdb_metadata)
pgp_payment_methods = PgpPaymentMethodTable(db_metadata=payin_paymentdb_metadata)
cart_payments = CartPaymentTable(db_metadata=payin_paymentdb_metadata)
payment_intents = PaymentIntentTable(db_metadata=payin_paymentdb_metadata)
pgp_payment_intents = PgpPaymentIntentTable(db_metadata=payin_paymentdb_metadata)
payment_intents_adjustment_history = PaymentIntentAdjustmentTable(
    db_metadata=payin_paymentdb_metadata
)
payment_charges = PaymentChargeTable(db_metadata=payin_paymentdb_metadata)
pgp_payment_charges = PgpPaymentChargeTable(db_metadata=payin_paymentdb_metadata)