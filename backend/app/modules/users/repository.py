"""Tenant-scoped user directory."""

from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.database.enums import UserStatus
from app.core.database.repository import TenantAwareRepository
from app.modules.roles.models import Role
from app.modules.tenants.models import Branch
from app.modules.users.models import User

UserRow = tuple[User, str | None, str | None, str | None, str | None]


class UserRepository(TenantAwareRepository[User]):
    model = User

    def _active_select(self):
        return self._base_select().where(
            User.deleted_at.is_(None),
            User.status != UserStatus.DELETED.value,
        )

    async def get_active_by_id(self, user_id: UUID) -> User:
        stmt = self._active_select().where(User.id == user_id)
        result = await self.session.scalar(stmt)
        if result is None:
            from app.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError()
        return result

    async def search(
        self,
        *,
        query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UserRow], int]:
        stmt = (
            select(User, Role.name, Role.code, Branch.name, Branch.code)
            .outerjoin(Role, Role.id == User.role_id)
            .outerjoin(Branch, Branch.id == User.branch_id)
            .where(
                User.tenant_id == self.ctx.tenant_id,
                User.deleted_at.is_(None),
                User.status != UserStatus.DELETED.value,
            )
        )
        stmt = self._apply_branch_scope(stmt)
        count_stmt = self._count_select().where(
            User.deleted_at.is_(None),
            User.status != UserStatus.DELETED.value,
        )
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                Role.name.ilike(like),
                Branch.name.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = (
                select(func.count())
                .select_from(User)
                .outerjoin(Role, Role.id == User.role_id)
                .outerjoin(Branch, Branch.id == User.branch_id)
                .where(
                    User.tenant_id == self.ctx.tenant_id,
                    User.deleted_at.is_(None),
                    User.status != UserStatus.DELETED.value,
                )
                .where(filt)
            )
            count_stmt = self._apply_branch_scope(count_stmt)

        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(User.full_name.asc()).offset(offset).limit(limit)
        rows = list((await self.session.execute(stmt)).all())
        return [
            (user, role_name, role_code, branch_name, branch_code)
            for user, role_name, role_code, branch_name, branch_code in rows
        ], total
