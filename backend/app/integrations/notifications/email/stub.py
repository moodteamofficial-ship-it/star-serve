"""No-op transport for tests and machines without SMTP credentials."""

from __future__ import annotations

from uuid import uuid4

from app.core.config import Settings
from app.integrations.notifications.email.message import OutboundEmail
from app.integrations.notifications.email.transport import EmailTransport
from app.integrations.notifications.ports import NotificationSendResult


class StubEmailTransport(EmailTransport):
    name = "EMAIL_STUB"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, message: OutboundEmail) -> NotificationSendResult:
        return NotificationSendResult(
            success=True,
            provider_message_id=f"eml_{uuid4().hex[:12]}",
            provider_name=self.name,
            raw={
                "to": message.to,
                "subject": message.subject,
                "body_len": len(message.text or ""),
                "html_len": len(message.html or ""),
                "from": message.from_address,
                "mode": "STUB",
                "template": message.template_code,
            },
        )
