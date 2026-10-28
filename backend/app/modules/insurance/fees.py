"""Agency-side fees layered on top of the insurer (Definite) premium."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.context import SecurityContext

MONTHLY_REFERRAL_COST = Decimal("50.00")


def is_monthly_cover_period(cover_period: str | None) -> bool:
    normalized = (cover_period or "").strip().lower()
    if not normalized:
        return False
    if "semi" in normalized or "install" in normalized:
        return False
    return "month" in normalized


def monthly_referral_cost(cover_period: str | None) -> Decimal:
    """Fixed KES 50 referral cost on monthly cover — on top of Definite's total."""
    return MONTHLY_REFERRAL_COST if is_monthly_cover_period(cover_period) else Decimal("0.00")


def cover_period_from_policy(policy: Any) -> str | None:
    """Read the billed cover period from the policy's stored proposal summary."""
    summary = getattr(policy, "provider_payload_summary", None)
    if isinstance(summary, dict):
        submitted = summary.get("submitted")
        if isinstance(submitted, dict):
            period = submitted.get("cover_period")
            if isinstance(period, str) and period.strip():
                return period.strip()
    return None


async def resolve_cover_period(
    session: AsyncSession, ctx: SecurityContext, policy: Any
) -> str | None:
    """Prefer the issuance summary; fall back to the linked proposal row."""
    period = cover_period_from_policy(policy)
    if period:
        return period
    proposal_id = getattr(policy, "proposal_id", None)
    if proposal_id is None:
        return None
    from app.core.exceptions import ResourceNotFoundError
    from app.modules.proposals.repository import ProposalRepository

    try:
        proposal = await ProposalRepository(session, ctx).get(UUID(str(proposal_id)))
    except ResourceNotFoundError:
        return None
    stored = getattr(proposal, "cover_period", None)
    return stored.strip() if isinstance(stored, str) and stored.strip() else None
