"""M-Pesa STK via Safaricom Daraja (Lipa na M-Pesa Online).

Credentials: MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_SHORTCODE,
MPESA_PASSKEY. Callback: ``POST …/webhooks/payments/mpesa`` (Safaricom JSON).

Local/dev without credentials uses a signed stub webhook (tests).
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
from app.integrations.payments.mpesa.callback_parse import parse_daraja_stk_callback
from app.integrations.payments.mpesa.daraja_client import DarajaClient
from app.integrations.payments.ports import (
    PaymentInitResult,
    PaymentProvider,
    WebhookVerificationResult,
)
from app.modules.payments.dev_charge import resolve_outbound_charge_kes


class MpesaProvider(PaymentProvider):
    name = "MPESA"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _live_daraja(self) -> bool:
        if not getattr(self.settings, "mpesa_live", True):
            return False
        return bool(
            (self.settings.mpesa_consumer_key or "").strip()
            and (self.settings.mpesa_consumer_secret or "").strip()
            and (self.settings.mpesa_shortcode or "").strip()
            and (self.settings.mpesa_passkey or "").strip()
        )

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
        if self.settings.is_production and not self._live_daraja():
            raise ValidationAppError("M-Pesa Daraja is not configured for this environment")

        charge = resolve_outbound_charge_kes(self.settings, amount)

        if not self._live_daraja():
            checkout_id = f"ws_CO_{uuid4().hex[:16]}"
            return PaymentInitResult(
                provider_checkout_id=checkout_id,
                status="PENDING",
                raw={
                    "MerchantRequestID": f"mr_{uuid4().hex[:10]}",
                    "CheckoutRequestID": checkout_id,
                    "ResponseCode": "0",
                    "CustomerMessage": "Success. Request accepted for processing",
                    "mode": "STUB",
                    "stk_amount": str(charge.quantize(Decimal("0.01"))),
                    "Amount": str(charge),
                    "Phone": phone,
                    "AccountReference": reference,
                },
            )

        client = DarajaClient(self.settings)
        try:
            raw = await client.stk_push(
                phone=phone,
                amount=charge,
                account_reference=reference,
                transaction_desc=str(metadata.get("policy_number") or "StarServe")[:13],
            )
        finally:
            await client.aclose()

        checkout_id = str(
            raw.get("CheckoutRequestID") or raw.get("checkoutRequestID") or ""
        ).strip()
        if not checkout_id:
            raise ValidationAppError("M-Pesa STK Push did not return CheckoutRequestID")

        return PaymentInitResult(
            provider_checkout_id=checkout_id,
            status="PENDING",
            raw={
                **raw,
                "mode": "DARAJA",
                "stk_amount": str(charge.quantize(Decimal("0.01"))),
                "AccountReference": reference,
            },
        )

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        if payload.get("Body") or payload.get("stkCallback"):
            flat = parse_daraja_stk_callback(payload)
            result_code = str(flat.get("ResultCode", "1"))
            success = result_code in {"0", "00000000"}
            amount_raw = flat.get("Amount")
            amount = Decimal(str(amount_raw)) if amount_raw not in (None, "") else None
            checkout = str(flat.get("CheckoutRequestID") or "").strip()
            reference = str(flat.get("AccountReference") or "").strip()
            return WebhookVerificationResult(
                valid=True,
                reference=reference,
                checkout_id=checkout,
                receipt=str(flat.get("MpesaReceiptNumber") or "") or None,
                amount=amount,
                currency="KES",
                success=success,
                failure_code=None if success else result_code,
                failure_message=None if success else str(flat.get("ResultDesc") or "Payment failed"),
                raw=payload,
                outcome_authenticated=True,
                identity_kind="checkout",
            )

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
