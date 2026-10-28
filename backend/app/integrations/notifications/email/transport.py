"""Email transport port — swap Gmail / SES / SendGrid without touching domain code."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.integrations.notifications.email.message import OutboundEmail
from app.integrations.notifications.ports import NotificationSendResult


class EmailTransport(ABC):
    """One outbound adapter. Implementations must be safe to call from many tasks."""

    name: str

    @abstractmethod
    async def send(self, message: OutboundEmail) -> NotificationSendResult:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None
