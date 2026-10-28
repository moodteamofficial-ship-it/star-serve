"""SMS via TextSMS (sms.textsms.co.ke).

Credentials come from ``SMS_API_KEY`` + ``SMS_PARTNER_ID`` (Secret Manager on
Cloud Run). They are never logged, returned, or stored on the notification row.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.notifications.ports import NotificationProvider, NotificationSendResult

logger = get_logger(__name__)

PROVIDER_NAME = "TEXTSMS"
_DEFAULT_URL = "https://sms.textsms.co.ke/api/services/sendsms/"
_MAX_MESSAGE_CHARS = 480
_LOCAL_MSISDN = re.compile(r"^0[17]\d{8}$")
_INTL_MSISDN = re.compile(r"^254[17]\d{8}$")


def to_local_msisdn(recipient: str | None) -> str | None:
    """Kenyan mobile as 07XXXXXXXX / 01XXXXXXXX (USSD / display helpers)."""
    digits = re.sub(r"\D", "", recipient or "")
    if digits.startswith("254") and len(digits) == 12:
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "0" + digits
    return digits if _LOCAL_MSISDN.match(digits) else None


def to_intl_msisdn(recipient: str | None) -> str | None:
    """Kenyan mobile as 2547XXXXXXXX / 2541XXXXXXXX (TextSMS ``mobile``)."""
    local = to_local_msisdn(recipient)
    if local is None:
        return None
    intl = "254" + local[1:]
    return intl if _INTL_MSISDN.match(intl) else None


def mask_msisdn(phone: str) -> str:
    return f"{phone[:4]}***{phone[-2:]}" if len(phone) >= 8 else "***"


def _message_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    responses = payload.get("responses")
    if isinstance(responses, list) and responses:
        first = responses[0]
        if isinstance(first, dict):
            for key in ("messageid", "messageId", "message_id", "id"):
                value = first.get(key)
                if value not in (None, ""):
                    return str(value)[:80]
    for key in ("messageid", "messageId", "message_id", "id", "requestId"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)[:80]
    return None


def _response_entry(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    responses = payload.get("responses")
    if isinstance(responses, list) and responses and isinstance(responses[0], dict):
        return responses[0]
    return None


def _provider_code(entry: dict[str, Any] | None) -> int | None:
    if not entry:
        return None
    # Official docs use "response-code"; some payloads typo "respose-code".
    raw = entry.get("response-code", entry.get("respose-code"))
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _response_summary(payload: Any) -> dict[str, Any]:
    entry = _response_entry(payload)
    if entry is None:
        if not isinstance(payload, dict):
            return {}
        out: dict[str, Any] = {}
        for key in ("success", "status", "message", "code"):
            value = payload.get(key)
            if isinstance(value, bool | int | float):
                out[key] = value
            elif isinstance(value, str):
                out[key] = value[:160]
        return out
    out = {}
    code = _provider_code(entry)
    if code is not None:
        out["response_code"] = code
    desc = entry.get("response-description") or entry.get("respose-description")
    if isinstance(desc, str) and desc:
        out["response_description"] = desc[:160]
    if entry.get("networkid") not in (None, ""):
        out["networkid"] = str(entry.get("networkid"))[:20]
    return out


def _is_success(http_status: int, payload: Any) -> bool:
    if not (200 <= http_status < 300):
        return False
    entry = _response_entry(payload)
    if entry is None:
        # Empty/unexpected body with HTTP 2xx — treat as soft success only if
        # provider returned a top-level success flag.
        return isinstance(payload, dict) and payload.get("success") is True
    code = _provider_code(entry)
    if code is None:
        return False
    return code == 200


class SmsNotificationProvider(NotificationProvider):
    channel = "SMS"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = http_client
        self._owns_client = http_client is None
        self._lock = asyncio.Lock()

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client is None or self._client.is_closed:
                timeout = max(float(self.settings.sms_timeout_seconds), 1.0)
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                    follow_redirects=False,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                )
                self._owns_client = True
            return self._client

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None and self._owns_client and not client.is_closed:
            await client.aclose()

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        body: str,
        metadata: dict[str, Any],
    ) -> NotificationSendResult:
        phone = to_intl_msisdn(recipient)
        if phone is None:
            return NotificationSendResult(
                success=False,
                provider_name=PROVIDER_NAME,
                error_code="INVALID_RECIPIENT",
                error_message="SMS recipient must be a Kenyan mobile number",
            )
        message = (body or "").strip()[:_MAX_MESSAGE_CHARS]
        if not message:
            return NotificationSendResult(
                success=False,
                provider_name=PROVIDER_NAME,
                error_code="REJECTED",
                error_message="SMS body is empty",
            )
        raw: dict[str, Any] = {"to": mask_msisdn(phone), "body_len": len(message)}

        api_key = (self.settings.sms_api_key or "").strip()
        partner_id = str(self.settings.sms_partner_id or "").strip()
        shortcode = (self.settings.sms_sender_id or "").strip() or "STARSERVE"
        if not api_key or not partner_id:
            if self.settings.is_production:
                return NotificationSendResult(
                    success=False,
                    provider_name=PROVIDER_NAME,
                    raw={**raw, "mode": "NOT_CONFIGURED"},
                    error_code="NOT_CONFIGURED",
                    error_message="SMS provider is not configured",
                )
            return NotificationSendResult(
                success=True,
                provider_message_id=f"sms_{uuid4().hex[:12]}",
                provider_name="SMS_STUB",
                raw={**raw, "mode": "STUB"},
            )

        url = (self.settings.sms_api_url or "").strip() or _DEFAULT_URL
        if not url.startswith("https://"):
            return NotificationSendResult(
                success=False,
                provider_name=PROVIDER_NAME,
                raw={**raw, "mode": "NOT_CONFIGURED"},
                error_code="NOT_CONFIGURED",
                error_message="SMS API URL must be https",
            )

        try:
            client = await self._http()
            response = await client.post(
                url,
                json={
                    "apikey": api_key,
                    "partnerID": partner_id,
                    "message": message,
                    "shortcode": shortcode,
                    "mobile": phone,
                },
            )
        except httpx.TimeoutException:
            logger.warning("sms_send_timeout", extra={"to": raw["to"]})
            return NotificationSendResult(
                success=False,
                provider_name=PROVIDER_NAME,
                raw={**raw, "mode": "LIVE"},
                error_code="TIMEOUT",
                error_message="SMS provider timed out",
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "sms_send_network_error", extra={"to": raw["to"], "error": type(exc).__name__}
            )
            return NotificationSendResult(
                success=False,
                provider_name=PROVIDER_NAME,
                raw={**raw, "mode": "LIVE"},
                error_code="NETWORK_ERROR",
                error_message="SMS provider unreachable",
            )

        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        raw = {
            **raw,
            "mode": "LIVE",
            "http_status": response.status_code,
            "response": _response_summary(payload),
        }
        status = response.status_code
        if _is_success(status, payload):
            return NotificationSendResult(
                success=True,
                provider_message_id=_message_id(payload) or f"sms_{uuid4().hex[:12]}",
                provider_name=PROVIDER_NAME,
                raw=raw,
            )

        provider_code = _provider_code(_response_entry(payload))
        if status in (401, 403) or provider_code in (401, 403):
            code, detail = "AUTH_FAILED", "SMS provider rejected the credentials"
        elif status == 429 or status >= 500 or (provider_code is not None and provider_code >= 500):
            code, detail = "PROVIDER_UNAVAILABLE", f"SMS provider returned HTTP {status}"
        else:
            code, detail = "REJECTED", f"SMS provider rejected the message (HTTP {status})"
        logger.warning(
            "sms_send_failed",
            extra={
                "to": raw["to"],
                "http_status": status,
                "provider_code": provider_code,
                "code": code,
            },
        )
        return NotificationSendResult(
            success=False,
            provider_name=PROVIDER_NAME,
            raw=raw,
            error_code=code,
            error_message=detail,
        )
