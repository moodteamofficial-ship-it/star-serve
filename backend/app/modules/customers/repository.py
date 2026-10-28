"""Tenant-scoped customer persistence."""

from uuid import UUID

from sqlalchemy import false, func, or_, select

from app.core.database.repository import TenantAwareRepository
from app.modules.customers.models import Customer
from app.modules.policies.models import Policy
from app.modules.proposals.models import Proposal


class CustomerRepository(TenantAwareRepository[Customer]):
    model = Customer

    def _apply_agent_scope(self, stmt):
        if not self.ctx.is_sales_agent:
            return stmt
        from app.modules.intermediaries.scope import customer_predicate

        return stmt.where(customer_predicate(self.ctx))

    def _active_select(self):
        return self._base_select().where(Customer.deleted_at.is_(None))

    async def get_active_by_id(self, customer_id: UUID) -> Customer:
        stmt = self._active_select().where(Customer.id == customer_id)
        result = await self.session.scalar(stmt)
        if result is None:
            from app.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError()
        return result

    async def find_by_id_number(self, id_number: str) -> Customer | None:
        """Staff CRM identity — never returns a guest-quote row."""
        from app.modules.customers.enums import CustomerOrigin

        stmt = self._active_select().where(
            Customer.id_number == id_number,
            Customer.origin == CustomerOrigin.STAFF.value,
        )
        return await self.session.scalar(stmt)

    async def find_by_phone(self, phone: str) -> Customer | None:
        """Staff CRM phone — never returns a guest-quote row."""
        from app.modules.customers.enums import CustomerOrigin

        stmt = self._active_select().where(
            Customer.phone == phone,
            Customer.origin == CustomerOrigin.STAFF.value,
        )
        return await self.session.scalar(stmt)

    async def find_by_email(self, email: str) -> Customer | None:
        """Staff CRM email — never returns a guest-quote row."""
        from app.modules.customers.enums import CustomerOrigin

        stmt = self._active_select().where(
            func.lower(Customer.email) == email.lower(),
            Customer.origin == CustomerOrigin.STAFF.value,
        )
        return await self.session.scalar(stmt)

    async def find_by_kra_pin(self, kra_pin: str) -> Customer | None:
        """Staff CRM KRA PIN — never returns a guest-quote row."""
        from app.modules.customers.enums import CustomerOrigin

        stmt = self._active_select().where(
            Customer.kra_pin == kra_pin,
            Customer.origin == CustomerOrigin.STAFF.value,
        )
        return await self.session.scalar(stmt)

    async def find_guest_by_session_id_number(
        self, id_number: str, guest_session_id: UUID
    ) -> Customer | None:
        from app.core.validation.identity import id_number_compact
        from app.modules.customers.enums import CustomerOrigin

        compact = id_number_compact(id_number)
        stmt = self._active_select().where(
            or_(
                Customer.id_number == id_number,
                func.replace(Customer.id_number, "-", "") == compact,
            ),
            Customer.origin == CustomerOrigin.GUEST.value,
            Customer.guest_session_id == guest_session_id,
        )
        return await self.session.scalar(stmt)

    async def search(
        self,
        *,
        query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Customer], int]:
        stmt = self._active_select()
        count_stmt = self._count_select().where(Customer.deleted_at.is_(None))
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                Customer.id_number.ilike(like),
                Customer.phone.ilike(like),
                Customer.first_name.ilike(like),
                Customer.last_name.ilike(like),
                Customer.email.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)

        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Customer.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, total

    async def display_names_by_ids(self, customer_ids: list[UUID]) -> dict[UUID, str]:
        """Return {customer_id: display name} for active customers."""
        if not customer_ids:
            return {}

        stmt = self._active_select().where(Customer.id.in_(customer_ids))
        rows = list((await self.session.scalars(stmt)).all())
        out: dict[UUID, str] = {}
        for row in rows:
            parts = [row.first_name, row.other_names, row.last_name]
            name = " ".join(part.strip() for part in parts if part and part.strip())
            out[row.id] = name
        return out

    async def activity_counts(
        self, customer_ids: list[UUID]
    ) -> dict[UUID, tuple[int, int]]:
        """Return {customer_id: (policies_count, proposals_count)} for the given ids."""
        if not customer_ids:
            return {}

        out: dict[UUID, tuple[int, int]] = {cid: (0, 0) for cid in customer_ids}

        from app.core.security.branch_scope import apply_branch_predicate

        policy_stmt = apply_branch_predicate(
            select(Policy.customer_id, func.count()).where(
                Policy.tenant_id == self.ctx.tenant_id,
                Policy.customer_id.in_(customer_ids),
            ),
            Policy,
            self.ctx,
        ).group_by(Policy.customer_id)
        if self.ctx.is_sales_agent:
            from app.modules.intermediaries.scope import policy_predicate

            policy_stmt = policy_stmt.where(policy_predicate(self.ctx))
        for customer_id, count in (await self.session.execute(policy_stmt)).all():
            policies, proposals = out[customer_id]
            out[customer_id] = (int(count), proposals)

        proposal_stmt = apply_branch_predicate(
            select(Proposal.customer_id, func.count()).where(
                Proposal.tenant_id == self.ctx.tenant_id,
                Proposal.customer_id.in_(customer_ids),
            ),
            Proposal,
            self.ctx,
        ).group_by(Proposal.customer_id)
        if self.ctx.is_sales_agent:
            proposal_stmt = proposal_stmt.where(
                Proposal.intermediary_id == self.ctx.agent_intermediary_id
                if self.ctx.agent_intermediary_id is not None
                else false()
            )
        for customer_id, count in (await self.session.execute(proposal_stmt)).all():
            policies, _ = out[customer_id]
            out[customer_id] = (policies, int(count))

        return out
