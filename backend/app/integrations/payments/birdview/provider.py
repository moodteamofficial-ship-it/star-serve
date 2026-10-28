"""BirdView STK payment provider — live outbound push + signed callback.

Architecture:
- ``initiate`` posts to BirdView ``/mobile-payments/stk-push`` (or local stub).
- ``callbackUrl`` embeds an HMAC over reference/amount/expiry. That token
  identifies the payment. It does not prove the outcome.
- Outcome is either a result HMAC (``sign_birdview_result``) or, for unsigned
  bodies, a CheckoutRequestID that must match the id stored at initiate.
- Optional ``birdview_test_amount`` (non-production) charges 1 KES etc. while the
  payment row keeps the authoritative policy premium.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.integrations.payments.birdview.client import BirdViewClient
from app.integrations.payments.ports import (
    PaymentInitResult,
    PaymentProvider,
    WebhookVerificationResult,
)


def _birdview_hmac_secret(settings: Settings) -> str | None:
    """Webhook HMAC key. Never fall back to CSRF_SECRET."""
    secret = (settings.birdview_webhook_secret or "").strip()
    return secret or None


def _callback_base(settings: Settings) -> str:
    base = (settings.birdview_callback_base_url or settings.mpesa_callback_base_url or "").rstrip(
        "/"
    )
    base = base or "http://localhost:8000"
    if settings.is_production and not settings.allow_insecure_production:
        if not base.lower().startswith("https://"):
            raise ValidationAppError("BirdView callback URL must be HTTPS in production")
    return base


# An STK prompt lives for ~2 minutes. A day-long callback window only widened the
# replay/leak surface of the URL token.
CALLBACK_TTL_SECONDS = 3600


def _hmac_hex(secret: str, canonical: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_birdview_callback(*, reference: str, amount: str, exp: int, secret: str) -> str:
    """Authenticates *the callback URL*: which payment, how much, until when.

    It deliberately says nothing about the outcome, because the outcome is not
    known when the URL is minted. Anything that asserts "paid" must be covered by
    ``sign_birdview_result`` (or vouched for by a source-IP allowlist).
    """
    return _hmac_hex(secret, f"{reference}|{amount}|{exp}")


def sign_birdview_result(
    *,
    reference: str,
    amount: str,
    exp: int,
    result_code: str,
    checkout_id: str,
    receipt: str,
    secret: str,
) -> str:
    """Authenticates *the outcome* — the part a URL token cannot prove."""
    canonical = f"{reference}|{amount}|{exp}|{result_code}|{checkout_id}|{receipt}"
    return _hmac_hex(secret, canonical)


def build_birdview_callback_url(
    *, reference: str, amount: Decimal, settings: Settings
) -> str:
    """Path + query token — HMAC binds reference, amount, and expiry."""
    secret = _birdview_hmac_secret(settings)
    if not secret:
        raise ValidationAppError("BirdView webhook secret is not configured")
    amt = str(amount.quantize(Decimal("0.01")))
    exp = int(time.time()) + CALLBACK_TTL_SECONDS
    token = sign_birdview_callback(reference=reference, amount=amt, exp=exp, secret=secret)
    prefix = settings.api_prefix.rstrip("/")
    query = urlencode({"ref": reference, "sig": token, "amt": amt, "exp": str(exp)})
    return (
        f"{_callback_base(settings)}{prefix}/webhooks/payments/birdview/"
        f"{reference}/{amt}/{exp}/{token}?{query}"
    )


def resolve_birdview_charge_amount(settings: Settings, amount: Decimal) -> Decimal:
    """Return STK charge; non-production defaults to 1 KES (see ``dev_charge``)."""
    from app.modules.payments.dev_charge import resolve_outbound_charge_kes

    return resolve_outbound_charge_kes(settings, amount)


def _dig(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _unwrap_stk(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Daraja Body.stkCallback and flat BirdView bodies."""
    body = payload.get("Body")
    if isinstance(body, dict):
        stk = body.get("stkCallback")
        if isinstance(stk, dict):
            return stk
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _metadata_map(stk: dict[str, Any]) -> dict[str, Any]:
    meta = stk.get("CallbackMetadata") or stk.get("callbackMetadata") or {}
    items = meta.get("Item") or meta.get("item") or []
    out: dict[str, Any] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("Name") or item.get("name")
            if name:
                out[str(name)] = item.get("Value", item.get("value"))
    return out


class BirdViewProvider(PaymentProvider):
    name = "BIRDVIEW"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: BirdViewClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or BirdViewClient(self.settings)

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
            raise ValidationAppError("BirdView currently supports KES only")
        if not phone:
            raise ValidationAppError("Phone number is required for BirdView payments")

        charge_amount = resolve_birdview_charge_amount(self.settings, amount)
        policy_number = str(metadata.get("policy_number") or reference)
        description = (
            f"Test {policy_number}" if charge_amount != amount else f"Premium {policy_number}"
        )[:100]
        callback_url = build_birdview_callback_url(
            reference=reference, amount=charge_amount, settings=self.settings
        )

        if not self.settings.birdview_live:
            checkout_id = f"bv_stub_{uuid4().hex[:16]}"
            return PaymentInitResult(
                provider_checkout_id=checkout_id,
                status="PENDING",
                raw={
                    "mode": "STUB",
                    "transactionReference": reference,
                    "CheckoutRequestID": checkout_id,
                    "Amount": str(amount),
                    "stk_amount": str(charge_amount),
                    "Phone": phone,
                    "callbackUrl": callback_url,
                    "CustomerMessage": "Stub STK accepted — send signed BirdView webhook to complete",
                },
            )

        raw = await self.client.stk_push(
            amount=charge_amount,
            phone=phone,
            transaction_reference=reference,
            transaction_description=description,
            callback_url=callback_url,
        )
        nested = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        checkout_id = str(
            _dig(
                nested if nested else raw,
                "CheckoutRequestID",
                "checkoutRequestId",
                "checkout_request_id",
                "transactionId",
                "transactionID",
                "id",
            )
            or _dig(
                raw,
                "CheckoutRequestID",
                "checkoutRequestId",
                "checkout_request_id",
                "transactionId",
                "transactionID",
                "id",
            )
            or ""
        )
        if not checkout_id:
            raise ValidationAppError("BirdView STK did not return a checkout id")
        return PaymentInitResult(
            provider_checkout_id=checkout_id,
            status="PENDING",
            raw={
                **raw,
                "mode": "LIVE",
                "transactionReference": reference,
                "callbackUrl": callback_url,
                "stk_amount": str(charge_amount),
                "policy_amount": str(amount.quantize(Decimal("0.01"))),
                "test_charge": charge_amount != amount,
                "MerchantRequestID": _dig(nested or raw, "MerchantRequestID", "merchantRequestId"),
                "CheckoutRequestID": checkout_id,
            },
        )

    def _verify_result_signature(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        reference: str,
        amount_signed: str,
        exp: int,
        result_code: str,
        checkout_id: str,
        receipt: str,
        secret: str,
    ) -> bool:
        """Return True when the *outcome* is covered by a provider signature.

        The URL token only proves the caller saw the callback URL. A result
        signature binds ResultCode, checkout id, and receipt. When the
        deployment requires that signature, unsigned success *and* failure
        are rejected here.
        """
        provided = str(
            headers.get("x-birdview-result-signature")
            or payload.get("rsig")
            or payload.get("result_signature")
            or ""
        )
        if not provided:
            if self.settings.birdview_result_signature_required:
                raise AuthenticationError("BirdView callback outcome is not signed")
            return False
        expected = sign_birdview_result(
            reference=reference,
            amount=amount_signed,
            exp=exp,
            result_code=result_code,
            checkout_id=checkout_id,
            receipt=receipt,
            secret=secret,
        )
        if not hmac.compare_digest(provided, expected):
            raise AuthenticationError("Invalid BirdView result signature")
        return True

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> WebhookVerificationResult:
        secret = _birdview_hmac_secret(self.settings)
        if not secret:
            raise AuthenticationError("BirdView webhook secret is not configured")
        # Prefer query/header/path token pair (we mint on initiate).
        lower = {k.lower(): v for k, v in headers.items()}
        sig = (
            lower.get("x-birdview-signature")
            or lower.get("x-starserve-signature")
            or str(payload.get("sig") or payload.get("signature") or "")
        )
        reference = str(
            payload.get("ref")
            or payload.get("transactionReference")
            or payload.get("AccountReference")
            or payload.get("reference")
            or ""
        )
        amount_signed = str(payload.get("amt") or "")
        exp_raw = payload.get("exp")
        if not reference or not sig or not amount_signed or exp_raw in (None, ""):
            raise AuthenticationError(
                "BirdView webhook missing reference, amount, expiry, or signature"
            )
        try:
            exp = int(exp_raw)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("BirdView webhook expiry is invalid") from exc
        if exp < int(time.time()):
            raise AuthenticationError("BirdView webhook expired")
        expected = sign_birdview_callback(
            reference=reference, amount=amount_signed, exp=exp, secret=secret
        )
        if not hmac.compare_digest(str(sig), expected):
            raise AuthenticationError("Invalid BirdView webhook signature")

        stk = _unwrap_stk(payload)
        meta = _metadata_map(stk)
        checkout_id = str(
            _dig(
                stk,
                "CheckoutRequestID",
                "checkoutRequestId",
                "checkout_request_id",
                "transactionId",
                "transactionID",
            )
            or _dig(payload, "CheckoutRequestID", "checkoutRequestId", "transactionId")
            or ""
        )
        result_code = _dig(stk, "ResultCode", "resultCode", "statusCode")
        if result_code is None:
            result_code = _dig(payload, "ResultCode", "resultCode", "statusCode")
        if result_code is None:
            raise AuthenticationError("BirdView webhook missing result code")
        success = str(result_code) in {"0", "00", "SUCCESS", "success", "COMPLETED"}
        amount_raw = (
            meta.get("Amount")
            or _dig(stk, "Amount", "amount")
            or _dig(payload, "Amount", "amount")
        )
        amount = Decimal(str(amount_raw)) if amount_raw is not None else None
        if success and amount is None:
            raise AuthenticationError("BirdView webhook missing amount")
        if amount is not None and Decimal(str(amount)).quantize(Decimal("0.01")) != Decimal(
            amount_signed
        ).quantize(Decimal("0.01")):
            raise AuthenticationError("BirdView webhook amount does not match signature")
        receipt = (
            str(
                meta.get("MpesaReceiptNumber")
                or _dig(stk, "MpesaReceiptNumber", "receiptNumber", "receipt", "ReceiptNumber")
                or _dig(payload, "MpesaReceiptNumber", "receiptNumber", "receipt")
                or ""
            )
            or None
        )
        if success:
            # A settlement with no traceable M-Pesa receipt cannot be reconciled
            # against the till, so it is not accepted as a settlement.
            if not receipt or not re.fullmatch(r"[A-Za-z0-9]{6,20}", receipt):
                raise AuthenticationError("BirdView webhook success without a valid receipt")
        outcome_authenticated = self._verify_result_signature(
            headers=lower,
            payload=payload,
            reference=reference,
            amount_signed=amount_signed,
            exp=exp,
            result_code=str(result_code),
            checkout_id=checkout_id,
            receipt=receipt or "",
            secret=secret,
        )
        return WebhookVerificationResult(
            valid=True,
            reference=reference,
            checkout_id=checkout_id or None,
            receipt=receipt,
            amount=amount,
            currency="KES",
            success=success,
            failure_code=None if success else str(result_code),
            failure_message=None
            if success
            else str(
                _dig(stk, "ResultDesc", "resultDesc", "message")
                or _dig(payload, "ResultDesc", "message")
                or "Payment failed"
            ),
            raw=payload,
            outcome_authenticated=outcome_authenticated,
            identity_kind="reference",
        )
