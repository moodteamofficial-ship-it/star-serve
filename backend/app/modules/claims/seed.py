"""Seed claim roles' approval limits and segregation policies for a tenant."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.claims.authorization import DEFAULT_DUTY_CONFLICTS
from app.modules.claims.models import ApprovalPolicy, SegregationPolicy
from app.modules.roles.models import Role

DEFAULT_APPROVAL_LIMITS: dict[str, tuple[Decimal, Decimal, bool, Decimal | None]] = {
    "claims_officer": (Decimal("0"), Decimal("50000"), False, None),
    "senior_claims_officer": (Decimal("0"), Decimal("250000"), False, None),
    "claims_manager": (Decimal("0"), Decimal("1000000"), True, Decimal("500000")),
}


async def seed_claim_governance(session: AsyncSession, tenant_id: UUID) -> None:
    roles = {
        row.code: row
        for row in (
            await session.scalars(select(Role).where(Role.tenant_id == tenant_id))
        ).all()
    }
    for code, (minimum, maximum, dual, threshold) in DEFAULT_APPROVAL_LIMITS.items():
        role = roles.get(code)
        if role is None:
            continue
        exists = await session.scalar(
            select(ApprovalPolicy).where(
                ApprovalPolicy.tenant_id == tenant_id,
                ApprovalPolicy.role_id == role.id,
            )
        )
        if exists is not None:
            continue
        session.add(
            ApprovalPolicy(
                tenant_id=tenant_id,
                role_id=role.id,
                minimum_amount=minimum,
                maximum_amount=maximum,
                claim_type="MOTOR",
                requires_second_approval=dual,
                second_approval_above=threshold,
                active=True,
            )
        )
    existing_pairs = {
        (row.left_duty, row.right_duty)
        for row in (
            await session.scalars(
                select(SegregationPolicy).where(SegregationPolicy.tenant_id == tenant_id)
            )
        ).all()
    }
    for left, right in DEFAULT_DUTY_CONFLICTS:
        if (left, right) in existing_pairs:
            continue
        session.add(
            SegregationPolicy(
                tenant_id=tenant_id,
                left_duty=left,
                right_duty=right,
                allowed=False,
                active=True,
            )
        )
    await session.flush()
