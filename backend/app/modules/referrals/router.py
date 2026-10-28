"""Customer referral credit routes (staff)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.referrals.models import CustomerReferralCredit
from app.modules.referrals.service import ReferralService, referral_link

router = APIRouter(prefix="/referrals", tags=["Referrals"])


class CustomerResendKitRequest(BaseModel):
    channel: Literal["EMAIL", "SMS", "WHATSAPP"]

    model_config = {"extra": "forbid"}

_REFERRAL_READ = (
    "commission:read",
    "commission:manage",
    "settings:manage",
    "tenant:manage",
)


def _entry_public(row: CustomerReferralCredit) -> dict:
    return {
        "id": str(row.id),
        "referral_code": row.referral_code,
        "entry_kind": row.entry_kind,
        "direction": row.direction,
        "amount": str(row.amount),
        "balance_after": str(row.balance_after),
        "currency": row.currency,
        "payment_id": str(row.payment_id) if row.payment_id else None,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "description": row.description,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
    }


@router.get("/accounts")
async def list_referral_accounts(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions(*_REFERRAL_READ))],
    q: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict:
    ctx.require_active_tenant()
    rows = await ReferralService(db).list_accounts(tenant_id=ctx.tenant_id, query=q, limit=limit)
    return success_response(
        {
            "items": [
                {
                    "referral_code": row.code,
                    "referral_link": referral_link(row.code),
                    "id_number": row.id_number,
                    "holder_name": row.holder_name,
                    "phone": row.phone,
                    "customer_id": str(row.customer_id) if row.customer_id else None,
                    "balance": str(row.balance),
                    "earned_total": str(row.earned_total),
                    "redeemed_total": str(row.redeemed_total),
                    "referrals": row.referrals,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/accounts/{referral_code}/entries")
async def list_referral_entries(
    referral_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions(*_REFERRAL_READ))],
) -> dict:
    ctx.require_active_tenant()
    rows = await ReferralService(db).list_entries(tenant_id=ctx.tenant_id, code=referral_code)
    return success_response(
        {"items": [_entry_public(row) for row in rows]},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/customers/{customer_id}")
async def customer_referral(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
) -> dict:
    """The customer's code (issued now if they predate referrals) and credit balance."""
    from app.modules.customers.repository import CustomerRepository

    ctx.require_staff_principal()
    customer = await CustomerRepository(db, ctx).get_active_by_id(customer_id)
    service = ReferralService(db)
    code = await service.ensure_code_for_customer(customer)
    balance = await service.balance(customer.tenant_id, customer.id_number)
    await db.commit()
    return success_response(
        {
            "referral_code": code.code if code else None,
            "referral_link": referral_link(code.code) if code else None,
            "balance": str(balance),
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/customers/{customer_id}/kit-channels")
async def customer_referral_kit_channels(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
) -> dict:
    """Enabled channels that can receive this customer's referral kit."""
    from app.modules.customers.repository import CustomerRepository

    ctx.require_staff_principal()
    customer = await CustomerRepository(db, ctx).get_active_by_id(customer_id)
    channels = await ReferralService(db).kit_channels_for_customer(customer)
    return success_response(
        {"channels": channels},
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/customers/{customer_id}/resend-kit")
async def resend_customer_referral_kit(
    customer_id: UUID,
    body: CustomerResendKitRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext, Depends(require_permissions("customer:update", "customer:create"))
    ],
) -> dict:
    from app.modules.customers.repository import CustomerRepository

    ctx.require_staff_principal()
    customer = await CustomerRepository(db, ctx).get_active_by_id(customer_id)
    service = ReferralService(db)
    data = await service.resend_kit_for_customer(
        ctx=ctx, customer=customer, channel=body.channel
    )
    await AuditService(db).record(
        action="customer.resend_referral_kit",
        resource="customer",
        resource_id=str(customer.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"channel": body.channel, "referral_code": data.get("referral_code")},
    )
    await db.commit()
    label = {"EMAIL": "Email", "SMS": "SMS", "WHATSAPP": "WhatsApp"}.get(
        body.channel, body.channel.title()
    )
    return success_response(
        data,
        message=f"Referral kit queued via {label}",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )
