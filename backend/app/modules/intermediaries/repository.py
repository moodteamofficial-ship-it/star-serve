"""Tenant-scoped intermediary repository."""

from uuid import UUID

from sqlalchemy import or_, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.intermediaries.models import Intermediary


class IntermediaryRepository(TenantAwareRepository[Intermediary]):
    model = Intermediary

    def _active_select(self):
        return self._base_select().where(Intermediary.deleted_at.is_(None))

    async def get_active_by_id(self, intermediary_id: UUID) -> Intermediary:
        stmt = self._active_select().where(Intermediary.id == intermediary_id)
        result = await self.session.scalar(stmt)
        if result is None:
            raise ResourceNotFoundError()
        return result

    async def find_by_identification(self, identification: str) -> Intermediary | None:
        stmt = self._active_select().where(Intermediary.identification == identification)
        return await self.session.scalar(stmt)

    async def find_by_agent_code(self, agent_code: str) -> Intermediary | None:
        stmt = self._active_select().where(Intermediary.agent_code == agent_code)
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Intermediary], int]:
        stmt = self._active_select()
        count_stmt = self._count_select().where(Intermediary.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Intermediary.status == status)
            count_stmt = count_stmt.where(Intermediary.status == status)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Intermediary.name.ilike(like),
                Intermediary.identification.ilike(like),
                Intermediary.agent_code.ilike(like),
                Intermediary.email.ilike(like),
                Intermediary.phone.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)

        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Intermediary.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, total
