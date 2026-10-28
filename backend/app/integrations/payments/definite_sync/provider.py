"""Settlement marker for the Definite wallet / Definite M-Pesa rails.

Definite ``initiatePayment`` is performed by ``DefiniteSettlementService`` before
this provider runs, so the local payment row and policy activation share one
code path with BirdView callbacks.

The insurer call means different things per rail, and this adapter must not
flatten that distinction:

* Wallet (method 3) debits agency float during the call — settlement is done.
* M-Pesa STK (method 1) only asks Definite to prompt the customer. Nobody has
  paid yet, so the local payment stays PENDING until the receipt is confirmed.

The rail decides, and the default is PENDING: an unknown or missing rail must
never mint a settled payment.
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.integrations.payments.ports import (
    PaymentInitResult,
    PaymentProvider,
    WebhookVerificationResult,
)
from app.modules.payments.settlement import PLANS, SettlementRail


def _settles_on_initiate(rail: str) -> bool:
    try:
        return PLANS[SettlementRail(rail)].settles_on_initiate
    except (KeyError, ValueError):
        return False


class DefiniteSyncPaymentProvider(PaymentProvider):
    name = "DEFINITE_SYNC"

    async def initiate(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        phone: str | None,
        metadata: dict[str, Any],
    ) -> PaymentInitResult:
        rail = str(metadata.get("settlement_rail") or "")
        settled = _settles_on_initiate(rail)
        return PaymentInitResult(
            provider_checkout_id=f"def_{uuid4().hex[:12]}",
            status="SUCCESS" if settled else "PENDING",
            receipt=(
                str(metadata.get("definite_receipt") or f"DEF-{reference[-8:]}")
                if settled
                else None
            ),
            raw={
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
                "settlement_rail": rail or "UNKNOWN",
                "phone": phone,
                "awaiting_confirmation": not settled,
            },
        )

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        return WebhookVerificationResult(valid=False)
