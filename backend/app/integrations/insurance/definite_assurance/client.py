"""HTTP client for Definite Assurance — timeouts, retries, circuit breaker.

Credentials never logged. Sensitive bodies truncated in logs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.logging.context import get_correlation_id, get_job_id, get_request_id
from app.integrations.insurance.definite_assurance.exceptions import (
    DefiniteAssuranceAuthError,
    DefiniteAssuranceError,
    DefiniteAssuranceUnavailable,
    DefiniteAssuranceValidationError,
)

logger = get_logger(__name__)

_SENSITIVE_KEYS = {"password", "pin", "authorization", "token", "secret"}

# Definite UAT sometimes returns a Windows Node stack instead of a business error.
_INTERNAL_PROVIDER_NOISE = (
    "fetch failed",
    "undici",
    "processticksandrejections",
    "index.js",
    "typeerror:",
    "econnreset",
    "econnrefused",
    "enotfound",
)

_PROVIDER_RETRY_MESSAGE = (
    "The insurer could not finish this step yet. Please try issuing the certificate again."
)


def provider_message_is_internal(text: str) -> bool:
    lower = (text or "").lower()
    return any(token in lower for token in _INTERNAL_PROVIDER_NOISE)


def public_definite_message(raw: str, *, fallback: str = _PROVIDER_RETRY_MESSAGE) -> str:
    text = (raw or "").strip()
    if not text or provider_message_is_internal(text):
        return fallback
    return text[:220]


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 8, recovery_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.failures = 0
        self.opened_at: float | None = None
        self.state = "CLOSED"

    def before_call(self) -> None:
        if self.state == "OPEN":
            assert self.opened_at is not None
            if time.monotonic() - self.opened_at >= self.recovery_seconds:
                self.state = "HALF_OPEN"
            else:
                raise DefiniteAssuranceUnavailable(
                    "The insurance service is temporarily unavailable. Please try again shortly."
                )

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold or self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.opened_at = time.monotonic()


def _scrub(payload: Any) -> Any:
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            if any(s in key.lower() for s in _SENSITIVE_KEYS):
                out[key] = "[REDACTED]"
            else:
                out[key] = _scrub(value)
        return out
    if isinstance(payload, list):
        return [_scrub(v) for v in payload[:20]]
    return payload


class DefiniteAssuranceClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        circuit: CircuitBreaker | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = http_client
        self._owns_client = http_client is None
        self.circuit = circuit or CircuitBreaker()
        self.base_url = self.settings.definite_assurance_base_url.rstrip("/") + "/"
        self.timeout = httpx.Timeout(
            self.settings.definite_assurance_timeout_seconds,
            connect=min(8.0, float(self.settings.definite_assurance_timeout_seconds)),
        )
        self._limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=40,
            keepalive_expiry=60.0,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if not self.settings.definite_assurance_username:
                raise DefiniteAssuranceUnavailable(
                    "Insurance provider credentials are not configured"
                )
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=self._limits,
                auth=(
                    self.settings.definite_assurance_username,
                    self.settings.definite_assurance_password,
                ),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "StarServe/1.0",
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retryable: bool = False,
        max_attempts: int = 3,
        timeout_seconds: float | None = None,
    ) -> Any:
        self.circuit.before_call()
        client = await self._get_client()
        url = path.lstrip("/")
        attempt = 0
        last_error: Exception | None = None
        timeout = (
            httpx.Timeout(timeout_seconds, connect=min(8.0, float(timeout_seconds)))
            if timeout_seconds
            else self.timeout
        )

        while attempt < max_attempts:
            attempt += 1
            started = time.perf_counter()
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=timeout,
                    headers={
                        "X-Request-ID": get_request_id() or "",
                        "X-Job-ID": get_job_id() or "",
                        "X-Correlation-ID": get_correlation_id() or "",
                    },
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "definite_assurance_request",
                    method=method,
                    path=url,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    # never log auth header / credentials
                    params=_scrub(params or {}),
                    body=_scrub(json_body or {}),
                )
                if response.status_code in {401, 403}:
                    self.circuit.record_failure()
                    raise DefiniteAssuranceAuthError()
                if response.status_code >= 500:
                    detail = _safe_error_body(response)
                    # Definite UAT often returns 500 for bad business payloads
                    # ("Error fetching data from the database") — don't trip the circuit.
                    if detail and detail not in {"provider_error", ""}:
                        raise DefiniteAssuranceValidationError(
                            detail if len(detail) < 220 else f"{detail[:200]}…",
                            details=[{"provider_status": response.status_code, "detail": detail, "path": url}],
                        )
                    self.circuit.record_failure()
                    if retryable and attempt < max_attempts:
                        await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
                        continue
                    raise DefiniteAssuranceUnavailable()
                if response.status_code == 404:
                    self.circuit.record_success()
                    return None
                if response.status_code >= 400:
                    # Do not retry validation errors
                    detail = _safe_error_body(response)
                    raise DefiniteAssuranceValidationError(
                        "The insurance provider rejected the request",
                        details=[{"provider_status": response.status_code, "detail": detail}],
                    )
                self.circuit.record_success()
                if not response.content:
                    parsed: Any = {}
                else:
                    try:
                        parsed = response.json()
                    except ValueError as exc:
                        raise DefiniteAssuranceError(
                            "Insurance provider returned an invalid response"
                        ) from exc
                if url.rstrip("/").split("/")[-1] in {"generateCertificate", "initiatePayment"}:
                    summary = parsed if isinstance(parsed, dict) else {}
                    logger.info(
                        "definite_assurance_response",
                        method=method,
                        path=url,
                        status_code=response.status_code,
                        success=summary.get("success") if summary else None,
                        message=str(summary.get("message") or summary.get("Message") or "")[:180],
                        keys=sorted(summary.keys())[:16] if summary else [],
                    )
                return parsed
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = exc
                self.circuit.record_failure()
                logger.warning(
                    "definite_assurance_transport_error",
                    method=method,
                    path=url,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                if retryable and attempt < max_attempts:
                    await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
                    continue
                raise DefiniteAssuranceUnavailable() from exc

        raise DefiniteAssuranceUnavailable() from last_error

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None, retryable: bool = True
    ) -> Any:
        return await self.request("GET", path, params=params, retryable=retryable)

    async def post(self, path: str, *, json_body: dict[str, Any], retryable: bool = False) -> Any:
        # Certificate / payment approval can exceed the default timeout on UAT.
        # Outer CertificateService already retries generateCertificate — keep HTTP
        # to one attempt there to avoid nested timeout stacks.
        normalized = path.lstrip("/")
        if normalized == "generateCertificate":
            return await self.request(
                "POST",
                path,
                json_body=json_body,
                retryable=False,
                max_attempts=1,
            )
        if normalized == "initiatePayment":
            return await self.request(
                "POST",
                path,
                json_body=json_body,
                retryable=True,
                max_attempts=2,
            )
        if normalized == "newProposal":
            # A retried proposal can leave an unpaid duplicate at Definite; that is
            # harmless (unpaid proposals lapse) compared with a 60s dead submit.
            return await self.request(
                "POST",
                path,
                json_body=json_body,
                retryable=True,
                max_attempts=2,
                timeout_seconds=self.settings.definite_assurance_proposal_timeout_seconds,
            )
        return await self.request("POST", path, json_body=json_body, retryable=retryable)


def _safe_error_body(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or data.get("detail")
            if msg:
                return public_definite_message(str(msg), fallback="provider_error")
        return "provider_error"
    except Exception:
        text = (response.text or "").strip()
        if not text:
            return "provider_error"
        # Definite UAT often returns HTML stack traces for SQL errors
        lower = text.lower()
        if "amountpaid" in lower and "null" in lower:
            return (
                "Definite rejected initiatePayment: AmountPaid was NULL "
                "(UAT parsing glitch — StarServe will retry int/string automatically)"
            )
        if "<pre>" in lower:
            start = lower.find("<pre>") + 5
            end = lower.find("</pre>", start)
            snippet = text[start:end if end > start else start + 240]
            snippet = (
                snippet.replace("<br>", " ")
                .replace("&nbsp;", " ")
                .replace("&#39;", "'")
                .strip()
            )
            return snippet[:300] if snippet else text[:200]
        return text[:300]


def absolute_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))
