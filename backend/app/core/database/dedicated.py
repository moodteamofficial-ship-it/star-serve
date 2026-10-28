"""Dedicated database bootstrap — register engines from tenant DSN config."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database.base import get_session_factory
from app.core.database.enums import DatabaseMode
from app.core.database.resolver import tenant_db_resolver
from app.core.logging import get_logger
from app.core.postgres_provider import detect_provider, resolve_engine_kwargs
from app.core.security.crypto import assert_dedicated_dsn_allowed, decrypt_secret
from app.modules.tenants.models import Tenant

logger = get_logger(__name__)

_dedicated_engines: dict[UUID, object] = {}


def register_tenant_dedicated_dsn(tenant_id: UUID, dsn: str) -> None:
    """Create (or replace) a dedicated session factory for a tenant."""
    settings = get_settings()
    provider = detect_provider(dsn)
    url, engine_kwargs, profile = resolve_engine_kwargs(
        database_url=dsn,
        provider=provider,
        ssl_mode=settings.db_ssl_mode,
        pool_size=max(2, settings.db_pool_size // 2),
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        command_timeout=settings.db_command_timeout,
        force_null_pool=settings.db_null_pool,
    )
    engine = create_async_engine(url, **engine_kwargs)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    tenant_db_resolver.register_dedicated(tenant_id, factory)
    _dedicated_engines[tenant_id] = engine
    logger.info(
        "dedicated_db_registered",
        extra={
            "tenant_id": str(tenant_id),
            "provider": profile.provider.value,
            "uses_pooler": profile.uses_pooler,
            "pool_mode": profile.pool_mode,
        },
    )


async def bootstrap_dedicated_databases() -> int:
    """Load DEDICATED_DATABASE tenants with DSN and register them (startup)."""
    from app.core.database.rls import set_rls_bypass

    factory = get_session_factory()
    count = 0
    async with factory() as session:
        await set_rls_bypass(session, True)
        rows = list(
            (
                await session.scalars(
                    select(Tenant).where(
                        Tenant.database_mode == DatabaseMode.DEDICATED_DATABASE.value,
                        Tenant.dedicated_database_dsn.is_not(None),
                    )
                )
            ).all()
        )
        for tenant in rows:
            if not tenant.dedicated_database_dsn:
                continue
            try:
                plaintext = decrypt_secret(
                    tenant.dedicated_database_dsn, require_envelope=True
                )
                if not plaintext:
                    continue
                plaintext = assert_dedicated_dsn_allowed(plaintext)
                register_tenant_dedicated_dsn(tenant.id, plaintext)
                count += 1
            except Exception:
                logger.exception(
                    "dedicated_db_register_failed",
                    extra={"tenant_id": str(tenant.id)},
                )
    return count


async def dispose_dedicated_engines() -> None:
    for engine in list(_dedicated_engines.values()):
        dispose = getattr(engine, "dispose", None)
        if dispose:
            await dispose()
    _dedicated_engines.clear()
