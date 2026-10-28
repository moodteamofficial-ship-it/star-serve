"""Tenant-aware repository base — all queries must be scoped."""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError, TenantAccessError
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext

ModelT = TypeVar("ModelT")


class TenantAwareRepository(Generic[ModelT]):
    """Centralizes tenant scoping so developers cannot forget WHERE tenant_id."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx

    def _base_select(self) -> Select[Any]:
        stmt = select(self.model)
        tenant_col = getattr(self.model, "tenant_id", None)
        if tenant_col is not None and not self.ctx.is_platform_admin:
            # Platform admins match RLS (see all tenants). App queries must not
            # hide guest-agency rows that staff need in payments/policies/etc.
            stmt = stmt.where(tenant_col == self.ctx.tenant_id)
        stmt = self._apply_branch_scope(stmt)
        return self._apply_agent_scope(stmt)

    def _apply_agent_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Sales Agent logins see only their own rows. Override per model."""
        return stmt

    def _apply_branch_scope(self, stmt: Select[Any]) -> Select[Any]:
        """Branch filter is fail-closed. Empty assignments are not tenant-wide.

        ``ALL_TENANT`` / guests / platform admins skip the filter. ``ASSIGNED``
        sees only those branches — ``NULL`` is not shared. ``NONE`` sees nothing.
        """
        if (
            self.ctx.is_guest
            or self.ctx.is_platform_admin
            or self.ctx.branch_scope == BranchScope.ALL_TENANT
        ):
            return stmt
        branch_col = getattr(self.model, "branch_id", None)
        if branch_col is None:
            return stmt
        if self.ctx.branch_scope == BranchScope.ASSIGNED and self.ctx.branch_ids:
            return stmt.where(branch_col.in_(self.ctx.branch_ids), branch_col.is_not(None))
        return stmt.where(false())

    def _count_select(self) -> Select[Any]:
        """COUNT with the same tenant + branch invariants as ``_base_select``."""
        stmt = select(func.count()).select_from(self.model)
        tenant_col = getattr(self.model, "tenant_id", None)
        if tenant_col is not None and not self.ctx.is_platform_admin:
            stmt = stmt.where(tenant_col == self.ctx.tenant_id)
        return self._apply_agent_scope(self._apply_branch_scope(stmt))

    def _owner_select(self, owner_column: str = "created_by_user_id") -> Select[Any]:
        """Tenant scope + only rows owned by the caller (unless elevated)."""
        stmt = self._base_select()
        if self.ctx.is_platform_admin or self.ctx.can_manage_users():
            return stmt
        owner_col = getattr(self.model, owner_column, None)
        if owner_col is not None:
            stmt = stmt.where(owner_col == self.ctx.user_id)
        return stmt

    async def get_by_id(self, entity_id: UUID) -> ModelT:
        stmt = self._base_select().where(getattr(self.model, "id") == entity_id)
        result = await self.session.scalar(stmt)
        if result is None:
            # Avoid leaking cross-tenant existence
            raise ResourceNotFoundError()
        return result

    async def add(self, entity: ModelT) -> ModelT:
        tenant_id = getattr(entity, "tenant_id", None)
        if tenant_id is not None and tenant_id != self.ctx.tenant_id:
            if not self.ctx.is_platform_admin:
                raise TenantAccessError("Cannot create resources for another tenant")
        self.session.add(entity)
        return entity

    async def list_page(self, *, offset: int, limit: int) -> list[ModelT]:
        stmt = self._base_select().offset(offset).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())
