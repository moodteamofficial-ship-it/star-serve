"""Notification provider port — SMS / Email / WhatsApp / Push adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NotificationSendResult:
    success: bool
    provider_message_id: str | None = None
    provider_name: str = "STUB"
    raw: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class NotificationProvider(ABC):
    channel: str

    @abstractmethod
    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        body: str,
        metadata: dict[str, Any],
    ) -> NotificationSendResult:
        raise NotImplementedError
