"""Notification provider factory."""

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.integrations.notifications.email.factory import (
    reset_email_transport,
    shutdown_email_transport,
)
from app.integrations.notifications.email.provider import EmailNotificationProvider
from app.integrations.notifications.ports import NotificationProvider
from app.integrations.notifications.sms.provider import SmsNotificationProvider
from app.integrations.notifications.whatsapp.provider import WhatsAppNotificationProvider
from app.modules.notifications.enums import NotificationChannel


@lru_cache
def _sms() -> SmsNotificationProvider:
    return SmsNotificationProvider(get_settings())


@lru_cache
def _email() -> EmailNotificationProvider:
    return EmailNotificationProvider(get_settings())


@lru_cache
def _whatsapp() -> WhatsAppNotificationProvider:
    return WhatsAppNotificationProvider(get_settings())


def get_notification_provider(channel: str) -> NotificationProvider:
    normalized = channel.upper()
    if normalized == NotificationChannel.SMS.value:
        return _sms()
    if normalized == NotificationChannel.EMAIL.value:
        return _email()
    if normalized == NotificationChannel.WHATSAPP.value:
        return _whatsapp()
    raise ValidationAppError(f"Unsupported notification channel: {channel}")


def reset_notification_providers() -> None:
    _sms.cache_clear()
    _email.cache_clear()
    _whatsapp.cache_clear()
    reset_email_transport()


async def shutdown_notification_providers() -> None:
    try:
        await shutdown_email_transport()
        if _sms.cache_info().currsize:
            await _sms().aclose()
    finally:
        reset_notification_providers()
