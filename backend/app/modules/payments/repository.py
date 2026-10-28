"""Tenant-scoped payment repository."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.payments.models import Payment


class PaymentRepository(TenantAwareRepository[Payment]):
    model = Payment

    def _apply_agent_scope(self, stmt):
        if not self.ctx.is_sales_agent:
            return stmt
        from app.modules.intermediaries.scope import payment_predicate

        return stmt.where(payment_predicate(self.ctx))

    async def get(self, payment_id: UUID) -> Payment:
        stmt = self._base_select().where(Payment.id == payment_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def get_for_update(self, payment_id: UUID) -> Payment:
        stmt = self._base_select().where(Payment.id == payment_id).with_for_update()
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def find_by_reference(self, reference: str) -> Payment | None:
        stmt = self._base_select().where(Payment.reference == reference)
        return await self.session.scalar(stmt)

    async def find_by_checkout_id(self, checkout_id: str) -> Payment | None:
        stmt = self._base_select().where(Payment.provider_checkout_id == checkout_id)
        return await self.session.scalar(stmt)

    async def find_latest_for_policy(self, policy_id: UUID, *, status: str | None = None) -> Payment | None:
        stmt = self._base_select().where(Payment.policy_id == policy_id)
        if status:
            stmt = stmt.where(Payment.status == status)
        stmt = stmt.order_by(Payment.created_at.desc()).limit(1)
        return await self.session.scalar(stmt)

    async def find_active_attempt_for_policy(self, policy_id: UUID) -> Payment | None:
        from app.modules.payments.enums import ACTIVE_PAYMENT_ATTEMPT_STATUSES

        stmt = (
            self._base_select()
            .where(
                Payment.policy_id == policy_id,
                Payment.status.in_(ACTIVE_PAYMENT_ATTEMPT_STATUSES),
            )
            .order_by(Payment.created_at.asc())
            .with_for_update()
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def find_success_for_policy(self, policy_id: UUID) -> Payment | None:
        from app.modules.payments.enums import PaymentStatus

        stmt = (
            self._base_select()
            .where(
                Payment.policy_id == policy_id,
                Payment.status == PaymentStatus.SUCCESS.value,
            )
            .order_by(Payment.paid_at.desc().nulls_last(), Payment.created_at.desc())
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
    ) -> tuple[list[Payment], int]:
        stmt = self._base_select()
        count_stmt = self._count_select()
        if status:
            stmt = stmt.where(Payment.status == status)
            count_stmt = count_stmt.where(Payment.status == status)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Payment.reference.ilike(like),
                Payment.provider_receipt.ilike(like),
                Payment.provider_checkout_id.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Payment.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total


async def find_payment_by_checkout_global(
    session: AsyncSession, checkout_id: str
) -> Payment | None:
    """Webhook lookup — bypass tenant filter; caller must set RLS after."""
    stmt = select(Payment).where(Payment.provider_checkout_id == checkout_id).with_for_update()
    return await session.scalar(stmt)


async def find_payment_by_reference_global(
    session: AsyncSession, reference: str
) -> Payment | None:
    """Webhook fallback when provider echoes transactionReference only."""
    stmt = select(Payment).where(Payment.reference == reference).with_for_update()
    return await session.scalar(stmt)
