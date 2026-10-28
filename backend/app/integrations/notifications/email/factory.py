"""Build the configured email transport. One process, one pooled adapter."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationAppError
from app.integrations.notifications.email.sendgrid import SendgridEmailTransport
from app.integrations.notifications.email.smtp import SmtpEmailTransport
from app.integrations.notifications.email.stub import StubEmailTransport
from app.integrations.notifications.email.transport import EmailTransport


def build_email_transport(settings: Settings | None = None) -> EmailTransport:
    cfg = settings or get_settings()
    kind = cfg.resolved_email_provider
    if kind == "stub":
        return StubEmailTransport(cfg)
    if kind in {"gmail", "smtp", "ses"}:
        return SmtpEmailTransport.from_settings(cfg)
    if kind == "sendgrid":
        return SendgridEmailTransport(cfg)
    raise ValidationAppError(f"Unsupported email provider: {kind}")


@lru_cache
def _transport() -> EmailTransport:
    return build_email_transport(get_settings())


def get_email_transport(settings: Settings | None = None) -> EmailTransport:
    if settings is not None and settings is not get_settings():
        return build_email_transport(settings)
    return _transport()


async def shutdown_email_transport() -> None:
    transport = _transport()
    await transport.aclose()
    _transport.cache_clear()


def reset_email_transport() -> None:
    _transport.cache_clear()
