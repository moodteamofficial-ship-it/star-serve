"""Resolve shared vs dedicated tenant database sessions.

Dedicated connections are registered from Tenant.dedicated_database_dsn
(see app.core.database.dedicated). Repository APIs stay mode-agnostic.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database.base import get_session_factory
from app.core.database.enums import DatabaseMode


class TenantDatabaseResolver:
    """Application services must not care which physical DB backs a tenant."""

    def __init__(self, shared_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._shared = shared_factory or get_session_factory()
        self._dedicated: dict[UUID, async_sessionmaker[AsyncSession]] = {}

    def register_dedicated(self, tenant_id: UUID, factory: async_sessionmaker[AsyncSession]) -> None:
        self._dedicated[tenant_id] = factory

    def unregister_dedicated(self, tenant_id: UUID) -> None:
        self._dedicated.pop(tenant_id, None)

    def has_dedicated(self, tenant_id: UUID) -> bool:
        return tenant_id in self._dedicated

    def session_factory(
        self,
        *,
        tenant_id: UUID | None,
        mode: DatabaseMode | str = DatabaseMode.SHARED_DATABASE,
    ) -> async_sessionmaker[AsyncSession]:
        mode_value = mode.value if isinstance(mode, DatabaseMode) else str(mode)
        if (
            mode_value == DatabaseMode.DEDICATED_DATABASE.value
            and tenant_id
            and tenant_id in self._dedicated
        ):
            return self._dedicated[tenant_id]
        return self._shared


tenant_db_resolver = TenantDatabaseResolver()
