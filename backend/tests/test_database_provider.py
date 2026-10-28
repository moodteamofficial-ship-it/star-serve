"""Unit tests for portable DB provider helpers — no live DB required."""

import json
from decimal import Decimal

from app.core.postgres_provider import (
    DatabaseProvider,
    detect_provider,
    normalize_asyncpg_url,
    prefers_transaction_pooler,
    redact_database_url,
    resolve_engine_kwargs,
)


def test_redact_strips_password() -> None:
    url = "postgresql+asyncpg://user:s3cret@db.example.com:5432/app"
    redacted = redact_database_url(url)
    assert "s3cret" not in redacted
    assert "user:***@" in redacted
    assert "db.example.com" in redacted


def test_detect_supabase() -> None:
    url = "postgresql+asyncpg://postgres:x@db.wbasegyvtchdmkfkyoei.supabase.co:5432/postgres"
    assert detect_provider(url) == DatabaseProvider.SUPABASE


def test_pooler_uses_queue_pool_by_default_with_no_statement_cache() -> None:
    """Long-lived API processes keep a small QueuePool; NullPool is opt-in."""
    url = (
        "postgresql+asyncpg://postgres.wbasegyvtchdmkfkyoei:pass@"
        "aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
    )
    _resolved, kwargs, profile = resolve_engine_kwargs(
        database_url=url,
        provider=DatabaseProvider.SUPABASE,
        ssl_mode="require",
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        command_timeout=30,
        force_null_pool=False,
    )
    assert prefers_transaction_pooler(url, DatabaseProvider.SUPABASE)
    assert profile.uses_pooler is True
    assert profile.pool_mode == "queue"
    assert "poolclass" not in kwargs
    assert kwargs["pool_size"] == 5
    assert kwargs["pool_pre_ping"] is False
    assert callable(kwargs["json_serializer"])
    assert json.loads(kwargs["json_serializer"]({"n": Decimal("4.50")})) == {"n": 4.5}
    assert kwargs["connect_args"].get("statement_cache_size") == 0
    assert "ssl" in kwargs["connect_args"]
    assert "pass" not in redact_database_url(url)


def test_force_null_pool_disables_pre_ping() -> None:
    url = (
        "postgresql+asyncpg://postgres.wbasegyvtchdmkfkyoei:pass@"
        "aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
    )
    _resolved, kwargs, profile = resolve_engine_kwargs(
        database_url=url,
        provider=DatabaseProvider.SUPABASE,
        ssl_mode="require",
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        command_timeout=30,
        force_null_pool=True,
    )
    assert profile.pool_mode == "null"
    assert "poolclass" in kwargs
    assert kwargs["pool_pre_ping"] is False


def test_normalize_postgres_scheme() -> None:
    assert normalize_asyncpg_url("postgres://a:b@h/db").startswith("postgresql+asyncpg://")
