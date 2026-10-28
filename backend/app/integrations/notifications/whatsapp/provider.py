"""WhatsApp notification provider — local stub."""

from typing import Any
from uuid import uuid4

from app.core.config import Settings, get_settings
from app.integrations.notifications.ports import NotificationProvider, NotificationSendResult


class WhatsAppNotificationProvider(NotificationProvider):
    channel = "WHATSAPP"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        body: str,
        metadata: dict[str, Any],
    ) -> NotificationSendResult:
        if not recipient or len(recipient) < 8:
            return NotificationSendResult(
                success=False,
                provider_name="WHATSAPP_STUB",
                error_code="INVALID_RECIPIENT",
                error_message="WhatsApp recipient must be a phone number",
            )
        msg_id = f"wa_{uuid4().hex[:12]}"
        mode = "LIVE_CONFIGURED" if self.settings.whatsapp_api_token else "STUB"
        return NotificationSendResult(
            success=True,
            provider_message_id=msg_id,
            provider_name="WHATSAPP_STUB" if mode == "STUB" else "WHATSAPP",
            raw={
                "to": recipient,
                "body_len": len(body),
                "mode": mode,
            },
        )
