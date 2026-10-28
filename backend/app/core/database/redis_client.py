"""Shared Redis client accessor for rate limits, cache, and readiness."""

from typing import Any

_redis_client: Any | None = None


def set_redis_client(client: Any | None) -> None:
    global _redis_client
    _redis_client = client


def get_redis_client() -> Any | None:
    return _redis_client


def redis_fail_closed() -> bool:
    """Fail closed only when a real Redis URL is configured for production.

    Cloud Run ships without Memorystore and defaults to ``localhost``, which
    never connects. Rate limits and guest sessions then use per-instance memory
    (and JWT session rebuild) — matching CLOUD_RUN.md.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.is_production:
        return False
    url = (settings.redis_url or "").strip().lower()
    if not url or "localhost" in url or "127.0.0.1" in url:
        return False
    return True
