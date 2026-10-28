"""Field-level claim responses — never SELECT * into the client."""

from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.context import SecurityContext
from app.modules.claims.authorization import PERM_PAY_READ, PERM_VIEW_SENSITIVE
from app.modules.claims.capabilities import compute_capabilities
from app.modules.claims.models import Claim
from app.modules.customers.models import Customer
from app.modules.policies.models import Policy
from app.modules.tenants.models import Tenant
from app.modules.users.models import User


def _customer_display_name(row: Customer | None) -> str | None:
    if row is None:
        return None
    parts = [row.first_name, row.other_names, row.last_name]
    return " ".join(part for part in parts if part) or None


def _agency_display_name(row: Tenant | None) -> str | None:
    if row is None:
        return None
    return row.trading_name or row.legal_name


def _money(value: Any) -> Any:
    return value


async def load_list_lookups(
    session: AsyncSession, claims: Iterable[Claim]
) -> tuple[dict[UUID, Customer], dict[UUID, Tenant], dict[UUID, str]]:
    rows = list(claims)
    if not rows:
        return {}, {}, {}
    customer_ids = {row.customer_id for row in rows}
    tenant_ids = {row.tenant_id for row in rows}
    user_ids = {row.assigned_to_user_id for row in rows if row.assigned_to_user_id}
    customers = {
        item.id: item
        for item in (
            await session.scalars(select(Customer).where(Customer.id.in_(customer_ids)))
        ).all()
    }
    tenants = {
        item.id: item
        for item in (await session.scalars(select(Tenant).where(Tenant.id.in_(tenant_ids)))).all()
    }
    names: dict[UUID, str] = {}
    if user_ids:
        names = {
            user_id: name
            for user_id, name in (
                await session.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
            ).all()
            if name
        }
    return customers, tenants, names


def to_list_item_named(
    ctx: SecurityContext,
    claim: Claim,
    *,
    customer_name: str | None,
    agency_name: str | None,
    assigned_to_name: str | None,
) -> dict[str, Any]:
    caps = compute_capabilities(ctx, claim)
    return {
        "id": str(claim.id),
        "claim_number": claim.claim_number,
        "status": claim.status,
        "claim_type": claim.claim_type,
        "policy_id": str(claim.policy_id),
        "customer_id": str(claim.customer_id),
        "customer_name": customer_name,
        "agency_name": agency_name,
        "vehicle_registration": claim.vehicle_registration,
        "claimed_amount": _money(claim.claimed_amount),
        "approved_amount": _money(claim.approved_amount)
        if ctx.allows(PERM_PAY_READ) or ctx.allows("claim:approve")
        else None,
        "currency": claim.currency,
        "assigned_to_user_id": str(claim.assigned_to_user_id) if claim.assigned_to_user_id else None,
        "assigned_to_name": assigned_to_name,
        "channel": claim.channel,
        "version": claim.version,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
        "capabilities": caps.model_dump(),
    }


def to_list_item_from_lookups(
    ctx: SecurityContext,
    claim: Claim,
    *,
    customers: dict[UUID, Customer],
    tenants: dict[UUID, Tenant],
    names: dict[UUID, str],
) -> dict[str, Any]:
    return to_list_item_named(
        ctx,
        claim,
        customer_name=_customer_display_name(customers.get(claim.customer_id)),
        agency_name=_agency_display_name(tenants.get(claim.tenant_id)),
        assigned_to_name=names.get(claim.assigned_to_user_id) if claim.assigned_to_user_id else None,
    )


async def to_list_items(
    session: AsyncSession, ctx: SecurityContext, claims: list[Claim]
) -> list[dict[str, Any]]:
    customers, tenants, names = await load_list_lookups(session, claims)
    return [
        to_list_item_from_lookups(
            ctx, claim, customers=customers, tenants=tenants, names=names
        )
        for claim in claims
    ]


async def to_list_item(
    session: AsyncSession, ctx: SecurityContext, claim: Claim
) -> dict[str, Any]:
    items = await to_list_items(session, ctx, [claim])
    return items[0]


async def load_detail_context(
    session: AsyncSession, claim: Claim
) -> tuple[Policy | None, Customer | None, Tenant | None, str | None]:
    assignee_name = (
        select(User.full_name).where(User.id == claim.assigned_to_user_id).scalar_subquery()
        if claim.assigned_to_user_id is not None
        else None
    )
    row = (
        await session.execute(
            select(Policy, Customer, Tenant, assignee_name)
            .select_from(Policy)
            .join(Customer, Customer.id == Policy.customer_id)
            .join(Tenant, Tenant.id == Policy.tenant_id)
            .where(Policy.id == claim.policy_id)
        )
    ).first()
    if row is None:
        return None, None, None, None
    return row[0], row[1], row[2], row[3]


def to_detail_payload(
    ctx: SecurityContext,
    claim: Claim,
    *,
    extras: dict[str, Any],
    policy: Policy | None,
    customer: Customer | None,
    tenant: Tenant | None,
    assigned_to_name: str | None,
    already_approved: bool = False,
) -> dict[str, Any]:
    sensitive = ctx.allows(PERM_VIEW_SENSITIVE)
    pay = ctx.allows(PERM_PAY_READ)
    caps = extras.get("capabilities") or compute_capabilities(
        ctx, claim, already_approved=already_approved
    )
    if hasattr(caps, "model_dump"):
        caps = caps.model_dump()
    payload: dict[str, Any] = {
        "id": str(claim.id),
        "claim_number": claim.claim_number,
        "status": claim.status,
        "claim_type": claim.claim_type,
        "channel": getattr(claim, "channel", None) or "STAFF",
        "agency_name": _agency_display_name(tenant),
        "version": claim.version,
        "policy": {
            "id": str(claim.policy_id),
            "policy_number": getattr(policy, "policy_number", None),
            "status": getattr(policy, "status", None),
            "product_code": getattr(policy, "product_code", None),
            "cover_option": getattr(policy, "cover_option", None),
            "cover_start_date": getattr(policy, "cover_start_date", None),
            "cover_end_date": getattr(policy, "cover_end_date", None),
        },
        "claimant": {
            "id": str(claim.customer_id),
            "name": _customer_display_name(customer),
            "phone": getattr(customer, "phone", None) if customer is not None else None,
            "id_number": getattr(customer, "id_number", None)
            if customer is not None and sensitive
            else None,
        },
        "accident": {
            "incident_date": claim.incident_date,
            "incident_time": claim.incident_time,
            "incident_location": claim.incident_location,
            "incident_description": claim.incident_description,
            "police_abstract_number": claim.police_abstract_number,
        },
        "vehicle": {
            "registration": claim.vehicle_registration,
            "make": claim.vehicle_make,
            "model": claim.vehicle_model,
            "chassis_number": claim.chassis_number if sensitive else None,
        },
        "driver": {
            "name": claim.driver_name,
            "license_number": claim.driver_license_number if sensitive else None,
        },
        "damage": {
            "description": claim.damage_description,
        },
        "injuries": {
            "summary": claim.injury_summary if sensitive else None,
            "medical_notes": claim.medical_notes if sensitive else None,
        },
        "financial": {
            "claimed_amount": claim.claimed_amount,
            "approved_amount": claim.approved_amount
            if pay or ctx.allows("claim:approve")
            else None,
            "currency": claim.currency,
            "beneficiary_type": claim.beneficiary_type if pay else None,
            "beneficiary_reference": claim.beneficiary_reference if pay else None,
        },
        "risk_assessment": claim.risk_assessment if sensitive else None,
        "assigned_to_user_id": str(claim.assigned_to_user_id) if claim.assigned_to_user_id else None,
        "assigned_to_name": assigned_to_name,
        "created_by_user_id": str(claim.created_by_user_id) if claim.created_by_user_id else None,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
        "submitted_at": claim.submitted_at,
        "closed_at": claim.closed_at,
        "capabilities": caps,
    }
    payload.update(extras)
    return payload


async def to_detail(
    session: AsyncSession,
    ctx: SecurityContext,
    claim: Claim,
    *,
    extras: dict[str, Any],
    already_approved: bool = False,
) -> dict[str, Any]:
    policy, customer, tenant, assigned_to_name = await load_detail_context(session, claim)
    return to_detail_payload(
        ctx,
        claim,
        extras=extras,
        policy=policy,
        customer=customer,
        tenant=tenant,
        assigned_to_name=assigned_to_name,
        already_approved=already_approved,
    )
