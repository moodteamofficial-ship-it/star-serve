"""Tenant-scoped branch directory."""

from uuid import UUID

from sqlalchemy import Select, false, func, or_, select

from app.core.database.repository import TenantAwareRepository
from app.core.security.branch_scope import BranchScope
from app.modules.tenants.models import Branch
from app.modules.users.models import User


class BranchRepository(TenantAwareRepository[Branch]):
    model = Branch

    def _apply_branch_scope(self, stmt: Select) -> Select:
        if (
            self.ctx.is_guest
            or self.ctx.is_platform_admin
            or self.ctx.branch_scope == BranchScope.ALL_TENANT
        ):
            return stmt
        if self.ctx.branch_scope == BranchScope.ASSIGNED and self.ctx.branch_ids:
            return stmt.where(Branch.id.in_(self.ctx.branch_ids))
        return stmt.where(false())

    def _active_select(self):
        return self._base_select().where(Branch.deleted_at.is_(None))

    async def get_active_by_id(self, branch_id: UUID) -> Branch:
        stmt = self._active_select().where(Branch.id == branch_id)
        result = await self.session.scalar(stmt)
        if result is None:
            from app.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError()
        return result

    async def find_by_code(self, code: str) -> Branch | None:
        stmt = self._active_select().where(func.lower(Branch.code) == code.lower())
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[tuple[Branch, int]], int]:
        user_count = (
            select(func.count())
            .select_from(User)
            .where(
                User.branch_id == Branch.id,
                User.deleted_at.is_(None),
                User.status != "DELETED",
            )
            .correlate(Branch)
            .scalar_subquery()
        )
        stmt = self._active_select().add_columns(user_count)
        count_stmt = self._count_select().where(Branch.deleted_at.is_(None))
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Branch.name.ilike(like),
                Branch.code.ilike(like),
                Branch.city.ilike(like),
                Branch.email.ilike(like),
                Branch.phone.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)

        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Branch.name.asc()).offset(offset).limit(limit)
        rows = list((await self.session.execute(stmt)).all())
        return [(row[0], int(row[1] or 0)) for row in rows], total
