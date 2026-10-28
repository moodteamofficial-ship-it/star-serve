"""Fail-closed provider configuration. Never log or return secret values."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError

_AGENT_MISSING = "Insurance agent is not configured"


def definite_integration_enabled(settings=None) -> bool:
    """True when this process is configured to call Definite."""
    cfg = settings or get_settings()
    return bool(
        (cfg.definite_assurance_username or "").strip()
        or (cfg.definite_assurance_password or "").strip()
    )


def require_configured_definite_agent(settings=None) -> str:
    """Return the configured Definite agent code, or fail closed.

    Guest input and hardcoded fallbacks must never choose the agent.
    """
    cfg = settings or get_settings()
    code = (cfg.definite_assurance_agent_code or "").strip()
    if not code:
        raise ValidationAppError(_AGENT_MISSING)
    return code
