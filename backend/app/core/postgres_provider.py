"""Portable Postgres providers — Supabase, Cloud SQL, local, generic.

Secrets (passwords, full DSNs) stay in env / Secret Manager only.
This module never serializes credentials into API responses.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.pool import NullPool

from app.core.jsoning import dumps_jsonb


class DatabaseProvider(StrEnum):
    LOCAL = "local"
    SUPABASE = "supabase"
    CLOUD_SQL = "cloud_sql"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class EngineConnectProfile:
    """Safe-to-log connection profile (no password / full DSN)."""

    provider: DatabaseProvider
    app_env: str
    host: str | None
    database: str | None
    uses_pooler: bool
    ssl_mode: str
    pool_mode: str  # "null" | "queue"


def detect_provider(database_url: str, explicit: str | None = None) -> DatabaseProvider:
    if explicit:
        try:
            return DatabaseProvider(explicit.lower().strip())
        except ValueError:
            pass
    host = (urlparse(database_url).hostname or "").lower()
    if "supabase.co" in host or "pooler.supabase.com" in host:
        return DatabaseProvider.SUPABASE
    if "cloudsql" in host or host.endswith(".sql.goog"):
        return DatabaseProvider.CLOUD_SQL
    if host in {"localhost", "127.0.0.1", "postgres", "db"}:
        return DatabaseProvider.LOCAL
    return DatabaseProvider.GENERIC


def redact_database_url(url: str) -> str:
    """Return a log-safe DSN with password stripped."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return "<invalid-url>"
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        if parsed.username:
            netloc = f"{parsed.username}:***@{netloc}"
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )
    except Exception:
        return "<redacted>"


def supabase_direct_host(project_ref: str) -> str:
    return f"db.{project_ref}.supabase.co"


def normalize_asyncpg_url(url: str) -> str:
    """Ensure SQLAlchemy asyncpg dialect prefix."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def prefers_transaction_pooler(url: str, provider: DatabaseProvider) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if provider == DatabaseProvider.SUPABASE:
        # Supabase transaction pooler is typically :6543 or *.pooler.supabase.com
        if "pooler.supabase" in host:
            return True
        if port == 6543:
            return True
    query = parse_qs(parsed.query)
    pool_mode = (query.get("pgbouncer") or query.get("pooler") or [""])[0].lower()
    return pool_mode in {"true", "1", "transaction"}


def build_ssl_connect_args(ssl_mode: str) -> dict[str, Any]:
    """Map DB_SSL_MODE to asyncpg connect args. Never disable SSL in production callers."""
    mode = (ssl_mode or "prefer").lower().strip()
    if mode in {"disable", "allow"}:
        return {}
    if mode == "require":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}
    if mode in {"verify-ca", "verify-full"}:
        return {"ssl": ssl.create_default_context()}
    # prefer / default: enable TLS when the server offers it (asyncpg wants explicit)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"ssl": ctx}


def resolve_engine_kwargs(
    *,
    database_url: str,
    provider: DatabaseProvider,
    ssl_mode: str,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    command_timeout: int,
    force_null_pool: bool = False,
) -> tuple[str, dict[str, Any], EngineConnectProfile]:
    """Build create_async_engine URL + kwargs tuned for Cloud Run + external poolers."""
    url = normalize_asyncpg_url(database_url)
    parsed = urlparse(url)
    uses_pooler = prefers_transaction_pooler(url, provider)

    connect_args: dict[str, Any] = {
        "command_timeout": command_timeout,
    }

    # Transaction-mode PgBouncer / Supabase pooler cannot use prepared statement caches
    if uses_pooler:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    # SSL: never force TLS against local sockets; require for remote managed Postgres
    host = (parsed.hostname or "").lower()
    is_local_host = host in {"localhost", "127.0.0.1", "::1", "postgres", "db"}
    effective_ssl = ssl_mode
    if is_local_host:
        effective_ssl = "disable" if ssl_mode not in {"verify-ca", "verify-full"} else ssl_mode
    elif provider in {DatabaseProvider.SUPABASE, DatabaseProvider.CLOUD_SQL} and ssl_mode in {
        "prefer",
        "allow",
        "disable",
    }:
        effective_ssl = "require"

    if effective_ssl not in {"disable", "allow"}:
        connect_args.update(build_ssl_connect_args(effective_ssl))

    # Strip libpq-only query params that confuse asyncpg
    if parsed.query:
        qs = parse_qs(parsed.query)
        for drop in ("sslmode", "pgbouncer", "pooler"):
            qs.pop(drop, None)
        clean_query = urlencode({k: v[0] for k, v in qs.items()})
        url = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment)
        )
        parsed = urlparse(url)

    # NullPool only when explicitly requested (serverless / many Cloud Run tasks).
    # Long-lived uvicorn should use a small QueuePool even against the transaction
    # pooler (statement cache already disabled) so TLS handshakes aren't per-request.
    use_null = force_null_pool
    engine_kwargs: dict[str, Any] = {
        # Remote pooler RTTs make pre-ping expensive; NullPool connections are fresh.
        "pool_pre_ping": False if (use_null or uses_pooler) else True,
        "connect_args": connect_args,
        # Decimal / UUID / datetime must survive JSONB writes (idempotency, payloads).
        "json_serializer": dumps_jsonb,
    }

    if use_null:
        engine_kwargs["poolclass"] = NullPool
        pool_mode = "null"
    else:
        # Keep app-side pools small — scale instances, not pool_size × 50k users.
        engine_kwargs.update(
            {
                "pool_size": max(1, pool_size),
                "max_overflow": max(0, max_overflow),
                "pool_timeout": pool_timeout,
            }
        )
        pool_mode = "queue"

    profile = EngineConnectProfile(
        provider=provider,
        app_env="",  # filled by caller
        host=parsed.hostname,
        database=(parsed.path or "/").lstrip("/") or None,
        uses_pooler=uses_pooler,
        ssl_mode=effective_ssl if provider != DatabaseProvider.LOCAL else ssl_mode,
        pool_mode=pool_mode,
    )
    return url, engine_kwargs, profile


def public_provider_label(provider: DatabaseProvider) -> str:
    return {
        DatabaseProvider.LOCAL: "Local PostgreSQL",
        DatabaseProvider.SUPABASE: "Supabase PostgreSQL",
        DatabaseProvider.CLOUD_SQL: "Google Cloud SQL",
        DatabaseProvider.GENERIC: "PostgreSQL",
    }[provider]
