"""SQLAlchemy base, mixins, and engine factory."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, MetaData, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.postgres_provider import resolve_engine_kwargs

logger = get_logger(__name__)

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """Never hard-delete rows — set status + deleted_at + deleted_by instead."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class UUIDPrimaryKeyMixin:
    id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TenantOwnedMixin:
    """Every tenant-owned row must include tenant_id."""

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url, engine_kwargs, profile = resolve_engine_kwargs(
            database_url=settings.database_url,
            provider=settings.resolved_db_provider,
            ssl_mode=settings.db_ssl_mode,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            command_timeout=settings.db_command_timeout,
            force_null_pool=settings.db_null_pool,
        )
        _engine = create_async_engine(url, **engine_kwargs)
        logger.info(
            "database_engine_created",
            extra={
                "provider": profile.provider.value,
                "app_env": settings.app_env,
                "host": profile.host,
                "database": profile.database,
                "uses_pooler": profile.uses_pooler,
                "pool_mode": profile.pool_mode,
                "ssl_mode": profile.ssl_mode,
                "dsn": settings.database_url_redacted,
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


# Re-export String for enums stored as varchar
__all__ = [
    "Base",
    "String",
    "SoftDeleteMixin",
    "TenantOwnedMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
]
