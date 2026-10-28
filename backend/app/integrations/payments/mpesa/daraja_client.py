"""Safaricom Daraja Lipa na M-Pesa Online (STK Push) — outbound only."""

from __future__ import annotations

import base64
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ExternalServiceError, ValidationAppError
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_SKEW_SECONDS = 30


def normalize_msisdn(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0") and len(digits) >= 10:
        digits = f"254{digits[1:]}"
    if digits.startswith("7") and len(digits) == 9:
        digits = f"254{digits}"
    if not digits.startswith("254") or len(digits) != 12:
        raise ValidationAppError("Phone number must be a valid Kenyan M-Pesa MSISDN (2547…)")
    return digits


def _stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f"{shortcode}{passkey}{timestamp}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


class DarajaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        base = (settings.mpesa_daraja_base_url or "https://api.safaricom.co.ke").rstrip("/")
        self.base_url = base
        timeout = max(5.0, float(getattr(settings, "mpesa_timeout_seconds", 30) or 30))
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _oauth_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - _TOKEN_SKEW_SECONDS:
            return self._token
        key = (self.settings.mpesa_consumer_key or "").strip()
        secret = (self.settings.mpesa_consumer_secret or "").strip()
        if not key or not secret:
            raise ValidationAppError("M-Pesa Daraja consumer key and secret are not configured")
        url = f"{self.base_url}/oauth/v1/generate"
        try:
            resp = await self._client.get(
                url,
                params={"grant_type": "client_credentials"},
                auth=(key, secret),
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("M-Pesa OAuth request failed") from exc
        if resp.status_code >= 400:
            logger.warning("daraja_oauth_failed", extra={"status": resp.status_code})
            raise ExternalServiceError("M-Pesa OAuth was rejected")
        data = resp.json()
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise ExternalServiceError("M-Pesa OAuth returned no access token")
        expires_in = int(data.get("expires_in") or 3599)
        self._token = token
        self._token_expires_at = now + max(60, expires_in)
        return token

    def callback_url(self) -> str:
        base = (
            (self.settings.mpesa_callback_base_url or "").strip()
            or (self.settings.birdview_callback_base_url or "").strip()
        ).rstrip("/")
        if not base:
            raise ValidationAppError("MPESA_CALLBACK_BASE_URL is not configured")
        if self.settings.is_production and not self.settings.allow_insecure_production:
            if not base.lower().startswith("https://"):
                raise ValidationAppError("M-Pesa callback URL must be HTTPS in production")
        prefix = (self.settings.api_prefix or "/api/v1").rstrip("/")
        return f"{base}{prefix}/webhooks/payments/mpesa"

    async def stk_push(
        self,
        *,
        phone: str,
        amount: Decimal,
        account_reference: str,
        transaction_desc: str,
    ) -> dict[str, Any]:
        shortcode = (self.settings.mpesa_shortcode or "").strip()
        passkey = (self.settings.mpesa_passkey or "").strip()
        if not shortcode or not passkey:
            raise ValidationAppError("M-Pesa shortcode and passkey are not configured")
        msisdn = normalize_msisdn(phone)
        amt = int(amount.quantize(Decimal("1"))) if amount == amount.to_integral_value() else float(
            amount.quantize(Decimal("0.01"))
        )
        ts = _timestamp()
        password = _stk_password(shortcode, passkey, ts)
        token = await self._oauth_token()
        ref = (account_reference or "StarServe")[:12]
        desc = (transaction_desc or "Insurance premium")[:13]
        body = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": ts,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amt,
            "PartyA": msisdn,
            "PartyB": shortcode,
            "PhoneNumber": msisdn,
            "CallBackURL": self.callback_url(),
            "AccountReference": ref,
            "TransactionDesc": desc,
        }
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        try:
            resp = await self._client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("M-Pesa STK Push request failed") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExternalServiceError("M-Pesa STK Push returned invalid JSON") from exc
        if resp.status_code >= 400:
            logger.warning(
                "daraja_stk_http_error",
                extra={"status": resp.status_code, "body": str(data)[:500]},
            )
            raise ExternalServiceError(
                str(data.get("errorMessage") or data.get("error") or "M-Pesa STK Push failed")
            )
        response_code = str(data.get("ResponseCode", ""))
        if response_code not in {"0", "00000000"}:
            raise ExternalServiceError(
                str(data.get("ResponseDescription") or "M-Pesa STK Push was not accepted")
            )
        return data
