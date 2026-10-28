"""Email notification provider — thin adapter over a swappable transport."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.integrations.notifications.email.factory import get_email_transport
from app.integrations.notifications.email.renderer import outbound_from_notification
from app.integrations.notifications.ports import NotificationProvider, NotificationSendResult
from app.integrations.notifications.email.message import EmailAttachment


class EmailNotificationProvider(NotificationProvider):
    channel = "EMAIL"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.transport = get_email_transport(self.settings)

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        body: str,
        metadata: dict[str, Any],
    ) -> NotificationSendResult:
        if "@" not in recipient:
            return NotificationSendResult(
                success=False,
                provider_name=self.transport.name,
                error_code="INVALID_RECIPIENT",
                error_message="Email recipient must be an email address",
            )
        extra = _extra_attachments(metadata.get("attachments"))
        message = outbound_from_notification(
            recipient=recipient.strip(),
            subject=subject,
            body=body,
            template_code=str(metadata.get("template") or "") or None,
            context=metadata.get("context") if isinstance(metadata.get("context"), dict) else {},
            settings=self.settings,
            notification_id=str(metadata.get("notification_id") or "") or None,
            extra_attachments=extra,
        )
        return await self.transport.send(message)

    async def aclose(self) -> None:
        await self.transport.aclose()


def _extra_attachments(raw: Any) -> list[EmailAttachment]:
    if not isinstance(raw, list):
        return []
    attachments: list[EmailAttachment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        filename = str(item.get("filename") or "").strip()
        if not filename or not isinstance(content, (bytes, bytearray)) or not content:
            continue
        content_type = str(item.get("content_type") or "application/pdf")
        content_id = str(item.get("content_id") or "").strip() or None
        attachments.append(
            EmailAttachment(
                filename=filename,
                content=bytes(content),
                content_type=content_type,
                content_id=content_id,
                inline=bool(item.get("inline")) and content_id is not None,
            )
        )
    return attachments
