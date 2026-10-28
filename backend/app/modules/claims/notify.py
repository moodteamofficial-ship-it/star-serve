"""Client notifications for claim events — never includes internal notes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ServiceDisabledError,
    TenantAccessError,
    ValidationAppError,
)
from app.core.security.context import SecurityContext
from app.modules.claims.models import Claim
from app.modules.customers.models import Customer
from app.modules.notifications.enums import NotificationChannel
from app.modules.notifications.schemas import NotificationSendRequest
from app.modules.notifications.service import NotificationService


async def notify_claim_event(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    claim: Claim,
    template: str,
    extra: dict[str, Any] | None = None,
) -> None:
    customer = await session.get(Customer, claim.customer_id)
    if customer is None:
        return
    # Staff notify is tenant-scoped. A platform admin acting on another
    # agency must not 404 the customer lookup and roll back the claim.
    if customer.tenant_id != ctx.tenant_id:
        return
    extra = extra or {}
    context = {
        "claim_id": str(claim.id),
        "claim_number": claim.claim_number,
        "policy_number": extra.get("policy_number", ""),
        "vehicle_registration": claim.vehicle_registration or "",
        "amount": str(claim.approved_amount or claim.claimed_amount),
        "currency": claim.currency,
        "status": claim.status,
        "recipient_name": " ".join(
            part for part in (customer.first_name, customer.last_name) if part
        ).strip(),
        "detail": extra.get("detail", ""),
        "followup_subject": extra.get("followup_subject", ""),
        "due_at": extra.get("due_at", ""),
    }
    targets: list[tuple[str, str]] = []
    email = (customer.email or "").strip()
    phone = (customer.phone or "").strip()
    if email:
        targets.append((NotificationChannel.EMAIL.value, email))
    elif phone:
        targets.append((NotificationChannel.SMS.value, phone))
    if not targets:
        return
    service = NotificationService(session, ctx)
    for channel, recipient in targets:
        try:
            await service.send(
                NotificationSendRequest(
                    channel=channel,
                    template_code=template,
                    recipient=recipient,
                    context=context,
                    customer_id=claim.customer_id,
                    related_resource="claim",
                    related_resource_id=claim.id,
                    deliver_now=True,
                ),
                from_staff=False,
            )
        except (
            ServiceDisabledError,
            ValidationAppError,
            ResourceNotFoundError,
            TenantAccessError,
            AuthorizationError,
        ):
            continue
