"""BirdView mobile-payments STK client.

Outbound only — credentials never logged. Callback verification lives on the
PaymentProvider adapter (HMAC token embedded in callbackUrl).

Some Kenyan ISP resolvers SERVFAIL ``payments.birdviewinsurance.com`` (CNAME to
Render). The same path on the Render hostname still works, so we try a
resolvable fallback when the branded host cannot be looked up.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import ExternalServiceError, ValidationAppError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Public CNAME target of payments.birdviewinsurance.com (Render).
DEFAULT_STK_FALLBACK_HOST = "payments-ewrv.onrender.com"


def kenya_phone_for_birdview(phone: str) -> str:
    """BirdView examples use national KE format (07xxxxxxxx)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("254") and len(digits) >= 12:
        return f"0{digits[3:12]}"
    if digits.startswith("0") and len(digits) >= 10:
        return digits[:10]
    if len(digits) == 9 and digits.startswith("7"):
        return f"0{digits}"
    raise ValidationAppError("Phone number must be a valid Kenyan M-Pesa MSISDN")


def amount_for_birdview(amount: Decimal) -> int | float:
    quantized = amount.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral_value():
        return int(quantized)
    return float(quantized)


def rewrite_url_host(url: str, host: str) -> str:
    parts = urlsplit(url)
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        netloc = f"{userinfo}@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def default_stk_fallback_url(primary: str) -> str:
    host = (urlsplit(primary).hostname or "").lower()
    if not host or host == DEFAULT_STK_FALLBACK_HOST:
        return ""
    if host.endswith("birdviewinsurance.com"):
        return rewrite_url_host(primary, DEFAULT_STK_FALLBACK_HOST)
    return ""


def host_resolves(host: str, *, port: int = 443) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def candidate_stk_urls(
    primary: str,
    *,
    fallback: str | None = None,
    resolves: Callable[[str], bool] | None = None,
) -> list[str]:
    """Prefer a host that resolves locally; keep the other URL as a retry."""
    primary = (primary or "").strip()
    fallback = (fallback or "").strip() or default_stk_fallback_url(primary)
    ordered: list[str] = []
    for url in (primary, fallback):
        if url and url not in ordered:
            ordered.append(url)
    if len(ordered) <= 1:
        return ordered
    check = resolves or (lambda hostname: host_resolves(hostname))

    def ok(url: str) -> bool:
        return check(urlsplit(url).hostname or "")

    ready = [url for url in ordered if ok(url)]
    blocked = [url for url in ordered if url not in ready]
    return ready + blocked


class BirdViewClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.timeout = httpx.Timeout(
            float(self.settings.birdview_timeout_seconds),
            connect=min(10.0, float(self.settings.birdview_timeout_seconds)),
        )

    async def stk_push(
        self,
        *,
        amount: Decimal,
        phone: str,
        transaction_reference: str,
        transaction_description: str,
        callback_url: str,
    ) -> dict[str, Any]:
        url = (self.settings.birdview_stk_url or "").strip()
        if not url:
            raise ValidationAppError("BirdView STK URL is not configured")

        payload = {
            "amount": amount_for_birdview(amount),
            "phoneNumber": kenya_phone_for_birdview(phone),
            "transactionDescription": transaction_description[:100],
            "transactionReference": transaction_reference[:64],
            "callbackUrl": callback_url,
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        api_key = (self.settings.birdview_api_key or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        targets = candidate_stk_urls(
            url, fallback=(self.settings.birdview_stk_fallback_url or "").strip() or None
        )
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for index, target in enumerate(targets):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(target, json=payload, headers=headers)
                if index > 0:
                    logger.warning(
                        "birdview_stk_used_fallback_host",
                        extra={
                            "host": urlsplit(target).hostname,
                            "reference": transaction_reference,
                        },
                    )
                break
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if index + 1 < len(targets):
                    logger.warning(
                        "birdview_stk_retry_alternate_host",
                        extra={
                            "from_host": urlsplit(target).hostname,
                            "to_host": urlsplit(targets[index + 1]).hostname,
                            "error_type": type(exc).__name__,
                            "reference": transaction_reference,
                        },
                    )
                    continue
                logger.warning(
                    "birdview_stk_unreachable",
                    extra={
                        "host": urlsplit(target).hostname,
                        "error_type": type(exc).__name__,
                        "reference": transaction_reference,
                    },
                )
                raise ExternalServiceError(
                    "M-Pesa prompt could not be sent. Please try again."
                ) from exc

        if response is None:
            raise ExternalServiceError(
                "M-Pesa prompt could not be sent. Please try again."
            ) from last_error

        body: dict[str, Any]
        try:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {"data": parsed}
        except Exception:
            body = {"raw": (response.text or "")[:500]}

        if response.status_code >= 400:
            logger.warning(
                "birdview_stk_failed",
                extra={
                    "status_code": response.status_code,
                    "reference": transaction_reference,
                },
            )
            message = (
                str(body.get("message") or body.get("error") or body.get("Message") or "")
                or f"BirdView STK failed ({response.status_code})"
            )
            raise ValidationAppError(message[:240])

        logger.info(
            "birdview_stk_accepted",
            extra={"status_code": response.status_code, "reference": transaction_reference},
        )
        return body
