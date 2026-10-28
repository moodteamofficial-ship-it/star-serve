"""Tenant-scoped certificate repository."""

from uuid import UUID

from sqlalchemy import select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.certificates.models import Certificate


class CertificateRepository(TenantAwareRepository[Certificate]):
    model = Certificate

    async def get(self, certificate_id: UUID) -> Certificate:
        stmt = self._base_select().where(Certificate.id == certificate_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def find_by_policy(self, policy_id: UUID) -> Certificate | None:
        stmt = (
            self._base_select()
            .where(Certificate.policy_id == policy_id)
            .order_by(Certificate.created_at.desc())
        )
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        policy_id: UUID | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Certificate], int]:
        stmt = self._base_select()
        count_stmt = self._count_select()
        if policy_id:
            stmt = stmt.where(Certificate.policy_id == policy_id)
            count_stmt = count_stmt.where(Certificate.policy_id == policy_id)
        if status:
            stmt = stmt.where(Certificate.status == status)
            count_stmt = count_stmt.where(Certificate.status == status)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Certificate.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total
