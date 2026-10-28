"""Customer business logic — tenant boundaries enforced via repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ValidationAppError
from app.core.security.branch_scope import resolve_authorized_branch
from app.core.security.context import SecurityContext
from app.core.security.media_url import sanitize_avatar_url
from app.core.validation.identity import normalize_id_number, normalize_kra_pin, normalize_phone
from app.modules.audit.service import AuditService
from app.modules.customers.enums import CustomerOrigin
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerCreateRequest, CustomerUpdateRequest
from app.modules.users.principals import require_assignable_tenant_user


def _public_avatar_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return sanitize_avatar_url(value, allowed_hosts=get_settings().avatar_url_hosts)
    except ValidationAppError:
        return None


def to_public(
    customer: Customer,
    *,
    policies_count: int = 0,
    proposals_count: int = 0,
) -> dict:
    return {
        "id": str(customer.id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "other_names": customer.other_names,
        "id_number": customer.id_number,
        "kra_pin": customer.kra_pin,
        "phone": customer.phone,
        "email": customer.email,
        "avatar_url": _public_avatar_url(customer.avatar_url),
        "logbook_url": customer.logbook_url,
        "id_front_url": customer.id_front_url,
        "id_back_url": customer.id_back_url,
        "date_of_birth": customer.date_of_birth,
        "status": customer.status,
        "branch_id": str(customer.branch_id) if customer.branch_id else None,
        "assigned_user_id": str(customer.assigned_user_id) if customer.assigned_user_id else None,
        "external_client_ref": customer.external_client_ref,
        "referral_code": getattr(customer, "referral_code", None),
        "referred_by_intermediary_id": (
            str(customer.referred_by_intermediary_id)
            if getattr(customer, "referred_by_intermediary_id", None)
            else None
        ),
        "referred_by_agent_code": getattr(customer, "referred_by_agent_code", None),
        "referred_by_agent_name": getattr(customer, "referred_by_agent_name", None),
        "referred_by_referral_code": getattr(customer, "referred_by_referral_code", None),
        "referred_at": getattr(customer, "referred_at", None),
        "policies_count": policies_count,
        "proposals_count": proposals_count,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
    }


class CustomerService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = CustomerRepository(session, ctx)
        self.audit = AuditService(session)

    async def create(self, body: CustomerCreateRequest) -> Customer:
        self.ctx.require_active_tenant()
        id_number = normalize_id_number(body.id_number)
        existing = await self.repo.find_by_id_number(id_number)
        if existing:
            raise ConflictError("A customer with this identification number already exists")

        phone = normalize_phone(body.phone)
        phone_owner = await self.repo.find_by_phone(phone)
        if phone_owner:
            raise ConflictError("A customer with this phone number already exists")

        email = str(body.email).lower() if body.email else None
        if email:
            email_owner = await self.repo.find_by_email(email)
            if email_owner:
                raise ConflictError("A customer with this email already exists")

        kra_pin = normalize_kra_pin(body.kra_pin)
        if kra_pin:
            kra_owner = await self.repo.find_by_kra_pin(kra_pin)
            if kra_owner:
                raise ConflictError("A customer with this KRA PIN already exists")

        branch_id = await resolve_authorized_branch(self.ctx, self.session, body.branch_id)
        customer = Customer(
            tenant_id=self.ctx.tenant_id,
            origin=CustomerOrigin.STAFF.value,
            guest_session_id=None,
            branch_id=branch_id,
            created_by_user_id=self.ctx.actor_user_id,
            assigned_user_id=self.ctx.actor_user_id,
            first_name=body.first_name.strip(),
            last_name=body.last_name.strip(),
            other_names=body.other_names.strip() if body.other_names else None,
            id_number=id_number,
            kra_pin=kra_pin,
            phone=phone,
            email=email,
            date_of_birth=body.date_of_birth,
            status="ACTIVE",
            notes=body.notes,
        )
        await self.repo.add(customer)
        await self.session.flush()
        from app.modules.referrals.service import ReferralService

        await ReferralService(self.session).ensure_code_for_customer(customer)
        await self.audit.record(
            action="customer.create",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"id_number": customer.id_number},
        )
        return customer

    async def lookup_by_id_number(self, id_number: str) -> Customer | None:
        """Staff-only local CRM lookup by national ID / passport."""
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        return await self.repo.find_by_id_number(normalize_id_number(id_number))

    async def last_vehicle(self, customer: Customer) -> dict | None:
        """Vehicle from the customer's latest proposal, to prefill a returning quote."""
        from app.modules.proposals.repository import ProposalRepository

        row = await ProposalRepository(self.session, self.ctx).latest_for_customer(customer.id)
        if row is None:
            return None
        return {
            "registration": row.vehicle_registration,
            "chassis_number": row.chassis_number,
            "engine_number": row.engine_number,
            "vehicle_year": row.vehicle_year,
            "engine_rating": row.engine_rating,
            "make_code": row.make_code,
            "make_name": row.vehicle_make,
            "model_code": row.model_code,
            "model_name": row.vehicle_model,
        }

    async def get(self, customer_id: UUID) -> Customer:
        self.ctx.require_staff_principal()
        return await self.repo.get_active_by_id(customer_id)

    async def list(
        self, *, page: int, limit: int, query: str | None
    ) -> tuple[list[Customer], int]:
        self.ctx.require_staff_principal()
        offset = (page - 1) * limit
        return await self.repo.search(query=query, offset=offset, limit=limit)

    async def list_public(
        self, *, page: int, limit: int, query: str | None
    ) -> tuple[list[dict], int]:
        rows, total = await self.list(page=page, limit=limit, query=query)
        counts = await self.repo.activity_counts([row.id for row in rows])
        items = [
            to_public(
                row,
                policies_count=counts.get(row.id, (0, 0))[0],
                proposals_count=counts.get(row.id, (0, 0))[1],
            )
            for row in rows
        ]
        return items, total

    async def update(self, customer_id: UUID, body: CustomerUpdateRequest) -> Customer:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        customer = await self.repo.get_active_by_id(customer_id)
        data = body.model_dump(exclude_unset=True)
        if "phone" in data and data["phone"] is not None:
            data["phone"] = normalize_phone(data["phone"])
            phone_owner = await self.repo.find_by_phone(data["phone"])
            if phone_owner and phone_owner.id != customer.id:
                raise ConflictError("A customer with this phone number already exists")
        if "kra_pin" in data:
            data["kra_pin"] = normalize_kra_pin(data["kra_pin"])
            if data["kra_pin"]:
                kra_owner = await self.repo.find_by_kra_pin(data["kra_pin"])
                if kra_owner and kra_owner.id != customer.id:
                    raise ConflictError("A customer with this KRA PIN already exists")
        if "email" in data and data["email"] is not None:
            data["email"] = str(data["email"]).lower()
            email_owner = await self.repo.find_by_email(data["email"])
            if email_owner and email_owner.id != customer.id:
                raise ConflictError("A customer with this email already exists")
        if "branch_id" in data:
            if not data["branch_id"]:
                raise ValidationAppError("Branch is required")
            data["branch_id"] = await resolve_authorized_branch(
                self.ctx, self.session, data["branch_id"]
            )
        self.ctx.assert_branch_access(customer.branch_id)
        if "avatar_url" in data:
            data["avatar_url"] = sanitize_avatar_url(
                data["avatar_url"],
                allowed_hosts=get_settings().avatar_url_hosts,
            )
        for key, value in data.items():
            setattr(customer, key, value)
        await self.session.flush()
        await self.audit.record(
            action="customer.update",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"fields": sorted(data.keys())},
        )
        return customer

    async def upload_kyc_document(
        self,
        customer_id: UUID,
        *,
        kind: str,
        payload: bytes,
        filename: str,
    ) -> dict:
        """Store logbook / ID scan on the customer and return the public locator."""
        self.ctx.require_active_tenant()
        customer = await self.repo.get_active_by_id(customer_id)
        self.ctx.assert_branch_access(customer.branch_id)
        from app.modules.customers.documents import store_customer_document

        stored = store_customer_document(
            tenant_id=self.ctx.tenant_id,
            customer_id=customer.id,
            kind=kind,
            payload=payload,
            filename=filename,
        )
        url = str(stored["url"])
        if kind == "logbook":
            customer.logbook_url = url
        elif kind == "id_front":
            customer.id_front_url = url
        elif kind == "id_back":
            customer.id_back_url = url
        else:
            raise ValidationAppError("Unknown document type")
        await self.session.flush()
        await self.audit.record(
            action="customer.kyc_document_upload",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"kind": kind, "url": url},
        )
        return {
            "kind": kind,
            "url": url,
            "customer": to_public(customer),
        }

    async def soft_delete(self, customer_id: UUID) -> None:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        from datetime import UTC, datetime

        customer = await self.repo.get_active_by_id(customer_id)
        customer.deleted_at = datetime.now(UTC)
        customer.deleted_by = self.ctx.user_id
        customer.status = "DELETED"
        await self.session.flush()
        await self.audit.record(
            action="customer.delete",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
        )

    async def assign(self, customer_id: UUID, assigned_user_id: UUID | None) -> Customer:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        customer = await self.repo.get_active_by_id(customer_id)
        if assigned_user_id is not None:
            await require_assignable_tenant_user(
                self.session,
                tenant_id=self.ctx.tenant_id,
                user_id=assigned_user_id,
            )
        customer.assigned_user_id = assigned_user_id
        await self.session.flush()
        await self.audit.record(
            action="customer.assign",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"assigned_user_id": str(assigned_user_id) if assigned_user_id else None},
        )
        return customer
