"""Wallet payment adapter — not a settlement rail.

Ledger credits/debits go through ``WalletService``. Issuance uses
``DEFINITE_WALLET`` (Definite initiatePayment method 3), never this adapter.
"""

from decimal import Decimal
from typing import Any

from app.core.exceptions import ValidationAppError
from app.integrations.payments.ports import (
    PaymentInitResult,
    PaymentProvider,
    WebhookVerificationResult,
)


class WalletPaymentProvider(PaymentProvider):
    """Hard-fail: returning SUCCESS here would activate a policy with no debit."""

    name = "WALLET"

    async def initiate(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        phone: str | None,
        metadata: dict[str, Any],
    ) -> PaymentInitResult:
        raise ValidationAppError(
            "Direct wallet SUCCESS without a ledger debit is not supported. "
            "Use DEFINITE_WALLET for insurer float settlement."
        )

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        return WebhookVerificationResult(valid=False)
