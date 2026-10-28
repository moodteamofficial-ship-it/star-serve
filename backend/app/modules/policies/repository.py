"""Tenant-scoped policy repository."""

from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.customers.models import Customer
from app.modules.policies.models import Policy


def compact_alnum(value: str) -> str:
    """Compare plates, POL, and certificate numbers as letters/digits only."""
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _alnum_col(column):
    return func.regexp_replace(func.upper(func.coalesce(column, "")), "[^A-Z0-9]", "", "g")


class PolicyRepository(TenantAwareRepository[Policy]):
    model = Policy

    def _apply_agent_scope(self, stmt):
        if not self.ctx.is_sales_agent:
            return stmt
        from app.modules.intermediaries.scope import policy_predicate

        return stmt.where(policy_predicate(self.ctx))

    async def get(self, policy_id: UUID) -> Policy:
        stmt = self._base_select().where(Policy.id == policy_id)
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def get_for_update(self, policy_id: UUID) -> Policy:
        stmt = self._base_select().where(Policy.id == policy_id).with_for_update()
        row = await self.session.scalar(stmt)
        if row is None:
            raise ResourceNotFoundError()
        return row

    async def find_unpaid_for_customer_vehicle(
        self,
        *,
        customer_id: UUID,
        registration: str,
        product_code: str,
        limit: int = 10,
    ) -> list[Policy]:
        from app.modules.policies.enums import PolicyStatus

        stmt = (
            self._base_select()
            .where(
                Policy.customer_id == customer_id,
                Policy.vehicle_registration == registration,
                Policy.product_code == product_code,
                Policy.status == PolicyStatus.PENDING_PAYMENT.value,
            )
            .order_by(Policy.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def find_by_number(self, policy_number: str) -> Policy | None:
        stmt = self._base_select().where(Policy.policy_number == policy_number)
        return await self.session.scalar(stmt)

    async def vehicle_registrations_by_ids(self, policy_ids: list[UUID]) -> dict[UUID, str]:
        if not policy_ids:
            return {}
        stmt = select(Policy.id, Policy.vehicle_registration).where(
            Policy.id.in_(policy_ids),
        )
        if not self.ctx.is_platform_admin:
            stmt = stmt.where(Policy.tenant_id == self.ctx.tenant_id)
        rows = (await self.session.execute(stmt)).all()
        return {policy_id: registration for policy_id, registration in rows}

    async def search(
        self,
        *,
        query: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Policy], int]:
        stmt = self._base_select()
        count_stmt = self._count_select()
        if status:
            stmt = stmt.where(Policy.status == status)
            count_stmt = count_stmt.where(Policy.status == status)
        if query:
            raw = query.strip()
            like = f"%{raw}%"
            compact = compact_alnum(raw)
            compact_like = f"%{compact}%" if len(compact) >= 3 else None
            name = func.concat_ws(
                " ", Customer.first_name, Customer.other_names, Customer.last_name
            )
            customer_hits = select(Customer.id).where(
                Customer.deleted_at.is_(None),
                or_(
                    name.ilike(like),
                    Customer.id_number.ilike(like),
                    Customer.phone.ilike(like),
                ),
            )
            if not self.ctx.is_platform_admin:
                customer_hits = customer_hits.where(Customer.tenant_id == self.ctx.tenant_id)
            parts = [
                Policy.policy_number.ilike(like),
                Policy.vehicle_registration.ilike(like),
                Policy.product_code.ilike(like),
                Policy.vehicle_make.ilike(like),
                Policy.vehicle_model.ilike(like),
                Policy.certificate_ref.ilike(like),
                Policy.provider_document_number.ilike(like),
                Policy.external_policy_ref.ilike(like),
                Policy.chassis_number.ilike(like),
                Policy.customer_id.in_(customer_hits),
            ]
            if compact_like:
                parts.extend(
                    [
                        _alnum_col(Policy.policy_number).like(compact_like),
                        _alnum_col(Policy.vehicle_registration).like(compact_like),
                        _alnum_col(Policy.certificate_ref).like(compact_like),
                        _alnum_col(Policy.provider_document_number).like(compact_like),
                        _alnum_col(Policy.external_policy_ref).like(compact_like),
                        _alnum_col(Policy.chassis_number).like(compact_like),
                    ]
                )
            filt = or_(*parts)
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Policy.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total
