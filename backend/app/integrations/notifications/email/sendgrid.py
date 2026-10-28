"""SendGrid Web API v3 — drop-in replacement for Gmail SMTP at higher volume."""

from __future__ import annotations

from uuid import uuid4

import httpx

from app.core.config import Settings
from app.integrations.notifications.email.message import OutboundEmail
from app.integrations.notifications.email.rate_limit import TokenBucket
from app.integrations.notifications.email.transport import EmailTransport
from app.integrations.notifications.ports import NotificationSendResult

_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


class SendgridEmailTransport(EmailTransport):
    name = "SENDGRID"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        limits = httpx.Limits(
            max_connections=settings.email_pool_size,
            max_keepalive_connections=settings.email_pool_size,
        )
        self._client = httpx.AsyncClient(timeout=20.0, limits=limits)
        self._limiter = TokenBucket(
            rate_per_second=settings.email_rate_limit_per_second,
            burst=settings.email_pool_size,
        )

    async def send(self, message: OutboundEmail) -> NotificationSendResult:
        key = (self.settings.email_api_key or "").strip()
        if not key:
            return NotificationSendResult(
                success=False,
                provider_name=self.name,
                error_code="NOT_CONFIGURED",
                error_message="EMAIL_API_KEY is required for SendGrid",
            )
        await self._limiter.acquire()
        content: list[dict[str, str]] = [{"type": "text/plain", "value": message.text or ""}]
        if message.html:
            content.append({"type": "text/html", "value": message.html})
        payload = {
            "personalizations": [{"to": [{"email": message.to}]}],
            "from": {
                "email": message.from_address,
                "name": message.from_name,
            },
            "subject": message.subject,
            "content": content,
            "headers": {
                "X-StarServe-Template": message.template_code or "",
                "X-StarServe-Notification": message.notification_id or "",
            },
        }
        if message.reply_to:
            payload["reply_to"] = {"email": message.reply_to}
        inline = []
        for item in message.attachments:
            import base64

            entry = {
                "content": base64.b64encode(item.content).decode("ascii"),
                "type": item.content_type,
                "filename": item.filename,
                "disposition": "inline" if item.inline else "attachment",
            }
            if item.content_id:
                entry["content_id"] = item.content_id
            inline.append(entry)
        if inline:
            payload["attachments"] = inline
        try:
            response = await self._client.post(
                _SEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            return NotificationSendResult(
                success=False,
                provider_name=self.name,
                error_code="SEND_FAILED",
                error_message=str(exc)[:500],
            )
        if response.status_code in {200, 202}:
            return NotificationSendResult(
                success=True,
                provider_message_id=(
                    response.headers.get("X-Message-Id") or f"sg_{uuid4().hex[:12]}"
                ),
                provider_name=self.name,
                raw={"status": response.status_code, "mode": "LIVE"},
            )
        retryable = response.status_code in {429, 500, 502, 503, 504}
        return NotificationSendResult(
            success=False,
            provider_name=self.name,
            error_code="TRANSIENT" if retryable else "REJECTED",
            error_message=f"SendGrid HTTP {response.status_code}",
        )

    async def aclose(self) -> None:
        await self._client.aclose()
