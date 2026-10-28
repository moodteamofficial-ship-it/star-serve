"""SMTP transport with a small per-thread connection cache.

Gmail, Google Workspace, Amazon SES SMTP, and generic relays share this path.
The event loop never blocks: send runs in a bounded thread pool so 200k queued
messages cannot stall FastAPI.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.notifications.email.message import OutboundEmail
from app.integrations.notifications.email.mime import build_mime
from app.integrations.notifications.email.rate_limit import TokenBucket
from app.integrations.notifications.email.transport import EmailTransport
from app.integrations.notifications.ports import NotificationSendResult

logger = get_logger(__name__)

_GMAIL_HOST = "smtp.gmail.com"
_TRANSIENT = frozenset({421, 450, 451, 452, 454, 455, 471})
_AUTH = frozenset({535, 534, 530})


@dataclass(frozen=True, slots=True)
class SmtpEndpoint:
    host: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    password: str
    timeout: float
    provider_name: str


def smtp_endpoint(settings: Settings) -> SmtpEndpoint:
    kind = settings.resolved_email_provider
    host = (settings.email_smtp_host or _GMAIL_HOST).strip()
    port = int(settings.email_smtp_port or 587)
    use_tls = bool(settings.email_smtp_use_tls)
    use_ssl = bool(settings.email_smtp_use_ssl)
    if kind == "gmail":
        host, port, use_tls, use_ssl = _GMAIL_HOST, 587, True, False
        name = "GMAIL_SMTP"
    elif kind == "ses":
        if not host or host == _GMAIL_HOST:
            region = (settings.email_ses_region or "eu-west-1").strip()
            host = f"email-smtp.{region}.amazonaws.com"
        name = "SES_SMTP"
    else:
        name = "SMTP"
    username = (settings.email_smtp_username or "").strip() or (settings.email_from_address or "")
    return SmtpEndpoint(
        host=host,
        port=port,
        use_tls=use_tls,
        use_ssl=use_ssl,
        username=username,
        password=settings.email_smtp_password_normalized,
        timeout=max(float(settings.email_smtp_timeout_seconds), 3.0),
        provider_name=name,
    )


class SmtpEmailTransport(EmailTransport):
    name = "SMTP"

    def __init__(self, settings: Settings, endpoint: SmtpEndpoint | None = None) -> None:
        self.settings = settings
        self.endpoint = endpoint or smtp_endpoint(settings)
        self.name = self.endpoint.provider_name
        workers = settings.email_pool_size
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="smtp")
        self._local = threading.local()
        self._limiter = TokenBucket(
            rate_per_second=settings.email_rate_limit_per_second,
            burst=max(workers, 2),
        )
        self._closed = False

    @classmethod
    def from_settings(cls, settings: Settings) -> SmtpEmailTransport:
        return cls(settings)

    async def send(self, message: OutboundEmail) -> NotificationSendResult:
        if self._closed:
            return NotificationSendResult(
                success=False,
                provider_name=self.name,
                error_code="TRANSPORT_CLOSED",
                error_message="Email transport is shutting down",
            )
        if not self.endpoint.password or not self.endpoint.username:
            return NotificationSendResult(
                success=False,
                provider_name=self.name,
                error_code="NOT_CONFIGURED",
                error_message="SMTP username and app password are required",
            )
        mime = build_mime(message)
        await self._limiter.acquire()
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(self._pool, self._send_sync, mime)
        except Exception as exc:
            return _map_error(self.name, exc)
        return NotificationSendResult(
            success=True,
            provider_message_id=str(mime["Message-ID"] or "")[:128] or None,
            provider_name=self.name,
            raw=raw,
        )

    def _send_sync(self, mime: EmailMessage) -> dict[str, Any]:
        client = self._client()
        try:
            refused = client.send_message(mime)
        except smtplib.SMTPServerDisconnected:
            self._drop_client()
            client = self._client()
            refused = client.send_message(mime)
        except Exception:
            self._drop_client()
            raise
        if refused:
            first = next(iter(refused.values()), (550, b"recipient refused"))
            code = int(first[0])
            msg = first[1] if len(first) > 1 else b"recipient refused"
            raise smtplib.SMTPResponseException(code, msg)
        return {
            "to": mime["To"],
            "host": self.endpoint.host,
            "mode": "LIVE",
        }

    def _client(self) -> smtplib.SMTP:
        existing = getattr(self._local, "smtp", None)
        if existing is not None:
            try:
                existing.noop()
                return existing
            except Exception:
                self._drop_client()
        ep = self.endpoint
        ctx = ssl.create_default_context()
        if ep.use_ssl:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(ep.host, ep.port, timeout=ep.timeout, context=ctx)
        else:
            smtp = smtplib.SMTP(ep.host, ep.port, timeout=ep.timeout)
            smtp.ehlo()
            if ep.use_tls:
                smtp.starttls(context=ctx)
                smtp.ehlo()
        smtp.login(ep.username, ep.password)
        self._local.smtp = smtp
        return smtp

    def _drop_client(self) -> None:
        smtp = getattr(self._local, "smtp", None)
        self._local.smtp = None
        if smtp is None:
            return
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                logger.debug("smtp_close_failed")

    async def aclose(self) -> None:
        self._closed = True
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._pool, self._drop_client)
        except Exception:
            logger.warning("smtp_pool_close_failed")
        self._pool.shutdown(wait=False, cancel_futures=True)


def _map_error(provider: str, exc: Exception) -> NotificationSendResult:
    code = getattr(exc, "smtp_code", None)
    msg = str(exc)
    redacted = _redact(msg)
    if isinstance(exc, smtplib.SMTPAuthenticationError) or code in _AUTH:
        return NotificationSendResult(
            success=False,
            provider_name=provider,
            error_code="AUTH_FAILED",
            error_message=(
                "SMTP authentication failed. Use a Gmail App Password, "
                "not the account password."
            ),
        )
    permanent = isinstance(exc, smtplib.SMTPRecipientsRefused) or (
        isinstance(code, int) and code >= 500 and code not in _TRANSIENT
    )
    if permanent:
        return NotificationSendResult(
            success=False,
            provider_name=provider,
            error_code="REJECTED",
            error_message=redacted[:500],
        )
    if isinstance(code, int) and code in _TRANSIENT:
        return NotificationSendResult(
            success=False,
            provider_name=provider,
            error_code="TRANSIENT",
            error_message=redacted[:500],
        )
    return NotificationSendResult(
        success=False,
        provider_name=provider,
        error_code="SEND_FAILED",
        error_message=redacted[:500],
    )


def _redact(text: str) -> str:
    return text.replace("\n", " ").strip()[:500]
