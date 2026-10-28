"""Tenant-scoped proposal repository."""

from uuid import UUID

from sqlalchemy import or_, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.proposals.enums import ProposalStatus
from app.modules.proposals.models import Proposal

OPEN_STATUSES = {
    ProposalStatus.DRAFT.value,
    ProposalStatus.PREMIUM_CALCULATED.value,
    ProposalStatus.DOUBLE_INSURANCE_CHECKED.value,
    ProposalStatus.SUBMITTED.value,
    ProposalStatus.APPROVED.value,
}


class ProposalRepository(TenantAwareRepository[Proposal]):
    model = Proposal

    async def get(self, proposal_id: UUID) -> Proposal:
        stmt = self._base_select().where(Proposal.id == proposal_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def find_open_for_vehicle_product(
        self, *, registration: str, product_code: str
    ) -> Proposal | None:
        stmt = self._base_select().where(
            Proposal.vehicle_registration == registration,
            Proposal.product_code == product_code,
            Proposal.status.in_(OPEN_STATUSES),
        )
        return await self.session.scalar(stmt)

    async def latest_for_customer(self, customer_id: UUID) -> Proposal | None:
        stmt = (
            self._base_select()
            .where(Proposal.customer_id == customer_id)
            .order_by(Proposal.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Proposal], int]:
        stmt = self._base_select()
        count_stmt = self._count_select()
        if status:
            stmt = stmt.where(Proposal.status == status)
            count_stmt = count_stmt.where(Proposal.status == status)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Proposal.vehicle_registration.ilike(like),
                Proposal.product_code.ilike(like),
                Proposal.external_proposal_ref.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Proposal.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total
