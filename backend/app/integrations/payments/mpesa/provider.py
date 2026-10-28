"""M-Pesa STK-style provider — local stub + webhook signature verification.

Real Safaricom Daraja credentials are configured via env; without them the
stub completes STK initiation as PENDING and accepts signed local webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.integrations.payments.ports import (
    PaymentInitResult,
    PaymentProvider,
    WebhookVerificationResult,
)


class MpesaProvider(PaymentProvider):
    name = "MPESA"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def initiate(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        phone: str | None,
        metadata: dict[str, Any],
    ) -> PaymentInitResult:
        if currency != "KES":
            raise ValidationAppError("M-Pesa currently supports KES only")
        if not phone:
            raise ValidationAppError("Phone number is required for M-Pesa payments")
        if self.settings.is_production and not (self.settings.mpesa_consumer_key or "").strip():
            raise ValidationAppError("M-Pesa is not configured for this environment")
        checkout_id = f"ws_CO_{uuid4().hex[:16]}"
        # Production would call Safaricom STK Push here with timeouts / no blind retries
        return PaymentInitResult(
            provider_checkout_id=checkout_id,
            status="PENDING",
            raw={
                "MerchantRequestID": f"mr_{uuid4().hex[:10]}",
                "CheckoutRequestID": checkout_id,
                "ResponseCode": "0",
                "CustomerMessage": "Success. Request accepted for processing",
                "mode": "STUB" if not self.settings.mpesa_consumer_key else "LIVE_CONFIGURED",
                "Amount": str(amount),
                "Phone": phone,
                "AccountReference": reference,
            },
        )

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        secret = (self.settings.mpesa_webhook_secret or "").strip()
        if not secret:
            raise AuthenticationError("M-Pesa webhook secret is not configured")
        signature = headers.get("x-starserve-signature") or headers.get("X-StarServe-Signature")
        ts = headers.get("x-starserve-timestamp") or headers.get("X-StarServe-Timestamp")
        if not ts:
            raise AuthenticationError("M-Pesa webhook timestamp is required")
        try:
            age = abs(time.time() - float(ts))
        except ValueError as exc:
            raise AuthenticationError("Invalid webhook timestamp") from exc
        if age > 300:
            raise AuthenticationError("Webhook timestamp outside allowed window")

        body_canonical = (
            str(payload.get("CheckoutRequestID", ""))
            + str(payload.get("Amount", ""))
            + str(payload.get("ResultCode", ""))
            + str(ts)
        )
        expected = hmac.new(
            secret.encode("utf-8"),
            body_canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            raise AuthenticationError("Invalid payment webhook signature")

        result_code = str(payload.get("ResultCode", "1"))
        success = result_code == "0"
        amount_raw = payload.get("Amount")
        amount = Decimal(str(amount_raw)) if amount_raw is not None else None
        return WebhookVerificationResult(
            valid=True,
            reference=str(payload.get("AccountReference") or payload.get("reference") or ""),
            checkout_id=str(payload.get("CheckoutRequestID") or ""),
            receipt=str(payload.get("MpesaReceiptNumber") or "") or None,
            amount=amount,
            currency="KES",
            success=success,
            failure_code=None if success else str(payload.get("ResultCode")),
            failure_message=None if success else str(payload.get("ResultDesc", "Payment failed")),
            raw=payload,
            outcome_authenticated=True,
            identity_kind="checkout",
        )


def sign_mpesa_webhook_stub(
    *,
    checkout_id: str,
    amount: str | Decimal,
    result_code: str = "0",
    timestamp: str,
    secret: str,
) -> str:
    body_canonical = f"{checkout_id}{amount}{result_code}{timestamp}"
    return hmac.new(secret.encode("utf-8"), body_canonical.encode("utf-8"), hashlib.sha256).hexdigest()
