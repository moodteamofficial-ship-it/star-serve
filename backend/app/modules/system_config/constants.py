"""System configuration keys and defaults."""

from typing import Any

KEY_OPERATIONAL = "system.operational"
KEY_SERVICES = "system.services"
KEY_NOTIFICATION_CHANNELS = "system.notification_channels"

DEFAULT_SERVICES: dict[str, bool] = {
    "quoting": True,
    "payments": True,
    "notifications": True,
    "issuance": True,
    "reports": True,
    "certificates": True,
    "claims": True,
}

SERVICE_KEYS = frozenset(DEFAULT_SERVICES)

DEFAULT_CHANNELS: dict[str, dict[str, Any]] = {
    "SMS": {"enabled": True},
    "EMAIL": {"enabled": True},
    "WHATSAPP": {"enabled": True},
    "PUSH": {"enabled": False},
}

CHANNEL_KEYS = frozenset(DEFAULT_CHANNELS)
