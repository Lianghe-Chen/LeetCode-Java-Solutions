from unittest import mock

import pytest
from app.commons.providers.stripe import stripe_models as models
from app.commons.providers.stripe.errors import StripeErrorType
from app.commons.providers.stripe.stripe_client import StripeClient
from app.commons.core.errors import PGPConnectionError, PGPApiError, PGPRateLimitError
from app.commons.providers.stripe.stripe_models import (
    RetrieveAccountRequest,
    Currency,
    Amount,
    StripeCreatePayoutRequest,
    StripeAccountId,
)
import stripe.error as stripe_error

from app.commons.types import CountryCode
from app.payout.core.errors import InstantPayoutInsufficientFundError
from app.payout.test_integration.utils import mock_stripe_account


class TestStripeClient:
    def setup(self):
        self.stripe_client = StripeClient(
            [models.StripeClientSettings(api_key="xxx", country="US")]
        )

    @pytest.fixture
    def mock_retrieve_stripe_account(self):
        with mock.patch("stripe.Account.retrieve") as mock_retrieve_stripe_account:
            yield mock_retrieve_stripe_account

    @pytest.fixture
    def mock_create_payout(self):
        with mock.patch("stripe.Payout.create") as mock_create_payout:
            yield mock_create_payout

    def test_retrieve_stripe_account_succeed(self, mock_retrieve_stripe_account):
        stripe_account_id = "acct_xxx"
        mock_retrieve_stripe_account.return_value = mock_stripe_account(
            stripe_account_id=stripe_account_id
        )
        # pass test if succeeded in getting account info from stripe
        try:
            self.stripe_client.retrieve_stripe_account(
                request=RetrieveAccountRequest(
                    country="US", account_id=stripe_account_id
                )
            )
        except Exception:
            raise Exception(
                "Retrieve stripe account should not raise exception when successfully"
                " get account info from stripe"
            )

    def test_retrieve_stripe_account_with_stripe_error_translation(
        self, mock_retrieve_stripe_account
    ):
        # Should return PGPConnectionError when stripe return APIConnectionError
        mock_retrieve_stripe_account.side_effect = stripe_error.APIConnectionError(
            "failed to connect to stripe"
        )

        with pytest.raises(PGPConnectionError):
            self.stripe_client.retrieve_stripe_account(
                request=RetrieveAccountRequest(country="US", account_id="acct_xxx")
            )

        # Should return PGPApiError when StripeError type is api_error
        json_body = {
            "error": {
                "type": StripeErrorType.api_error,
                "message": "Sorry! There was an error while talking to one of our backends. We have already been "
                "notified of the problem, but please contact support@stripe.com with any questions "
                "you may have.",
            }
        }
        mock_retrieve_stripe_account.side_effect = stripe_error.StripeError(
            json_body=json_body, message=json_body["error"]["message"]
        )

        with pytest.raises(PGPApiError):
            self.stripe_client.retrieve_stripe_account(
                request=RetrieveAccountRequest(country="US", account_id="acct_xxx")
            )

        # Should return PGPRateLimitError when StripeError code is api_error
        json_body = {
            "error": {
                "code": "rate_limit",
                "doc_url": "https://stripe.com/docs/error-codes/rate-limit",
                "message": "Request rate limit exceeded. You can learn more about rate limits here "
                "https://stripe.com/docs/rate-limits.",
                "type": "invalid_request_error",
            }
        }
        mock_retrieve_stripe_account.side_effect = stripe_error.StripeError(
            json_body=json_body, message=json_body["error"]["message"]
        )

        with pytest.raises(PGPRateLimitError):
            self.stripe_client.retrieve_stripe_account(
                request=RetrieveAccountRequest(country="US", account_id="acct_xxx")
            )

    def test_create_payout_insufficient_fund_error_with_stripe_error_translation(
        self, mock_create_payout
    ):
        # stripe insufficient fund error body
        json_body = {
            "error": {
                "code": "balance_insufficient",
                "doc_url": "https://stripe.com/docs/error-codes/balance-insufficient",
                "message": "Insufficient funds in Stripe account.    You can use the the /v1/balance endpoint to view "
                "your Stripe balance (for more details, see stripe.com/docs/api#balance).",
                "type": "invalid_request_error",
            }
        }
        mock_create_payout.side_effect = stripe_error.StripeError(
            json_body=json_body, message=json_body["error"]["message"]
        )
        with pytest.raises(InstantPayoutInsufficientFundError):
            self.stripe_client.create_payout_with_stripe_error_translation(
                country=CountryCode.US,
                currency=Currency("usd"),
                stripe_account=StripeAccountId("acct_xxx"),
                amount=Amount(999),
                request=StripeCreatePayoutRequest(),
            )
