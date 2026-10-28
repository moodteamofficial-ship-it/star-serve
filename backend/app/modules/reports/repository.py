"""Tenant-scoped report run repository."""

from uuid import UUID

from sqlalchemy import func, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.core.security.branch_scope import BranchScope
from app.modules.reports.models import ReportRun


class ReportRepository(TenantAwareRepository[ReportRun]):
    model = ReportRun

    def _visibility_select(self):
        """Assigned staff cannot read tenant-wide summaries another role stored."""
        stmt = self._base_select()
        if (
            not self.ctx.is_guest
            and not self.ctx.is_platform_admin
            and self.ctx.branch_scope != BranchScope.ALL_TENANT
        ):
            if self.ctx.branch_scope != BranchScope.ASSIGNED or not self.ctx.user_id:
                from sqlalchemy import false

                return stmt.where(false())
            stmt = stmt.where(ReportRun.created_by_user_id == self.ctx.user_id)
        return stmt

    async def get(self, report_id: UUID) -> ReportRun:
        stmt = self._visibility_select().where(ReportRun.id == report_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def search(
        self,
        *,
        report_type: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ReportRun], int]:
        stmt = self._visibility_select()
        if report_type:
            stmt = stmt.where(ReportRun.report_type == report_type)
        if status:
            stmt = stmt.where(ReportRun.status == status)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(ReportRun.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total
