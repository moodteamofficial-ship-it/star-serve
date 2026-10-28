"""Proposal HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.proposals.schemas import (
    ProposalCreateRequest,
    ProposalPublic,
    ProposalRejectRequest,
)
from app.modules.proposals.service import ProposalService, to_public
from app.modules.system_config.deps import require_system_service

router = APIRouter(prefix="/proposals", tags=["Proposals"])


def _provider() -> InsuranceProvider:
    return get_insurance_provider()


@router.post("")
async def create_proposal(
    body: ProposalCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:create"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    _: Annotated[None, Depends(require_system_service("quoting"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    service = ProposalService(db, ctx, provider)
    data = await service.create(body, idempotency_key=idempotency_key)
    await db.commit()
    return success_response(
        {
            "proposal": ProposalPublic.model_validate(data["proposal"]).model_dump(mode="json"),
            "job_id": data["job_id"],
        },
        message="Proposal created",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.get("")
async def list_proposals(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = ProposalService(db, ctx, provider)
    rows, total = await service.list(page=page, limit=limit, query=q, status=status)
    return success_response(
        {
            "items": [
                ProposalPublic.model_validate(to_public(r)).model_dump(mode="json") for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = ProposalService(db, ctx, provider)
    row = await service.get(proposal_id)
    return success_response(
        ProposalPublic.model_validate(to_public(row)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:approve"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = ProposalService(db, ctx, provider)
    row = await service.approve(proposal_id)
    await db.commit()
    return success_response(
        ProposalPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Proposal approved",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    body: ProposalRejectRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:approve"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = ProposalService(db, ctx, provider)
    row = await service.reject(proposal_id, reason=body.reason)
    await db.commit()
    return success_response(
        ProposalPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Proposal rejected",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{proposal_id}/cancel")
async def cancel_proposal(
    proposal_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("proposal:update"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = ProposalService(db, ctx, provider)
    row = await service.cancel(proposal_id)
    await db.commit()
    return success_response(
        ProposalPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Proposal cancelled",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{proposal_id}/issue-policy")
async def issue_policy_from_proposal(
    proposal_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:create"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    _: Annotated[None, Depends(require_system_service("issuance"))],
) -> dict:
    from app.modules.policies.schemas import PolicyPublic
    from app.modules.policies.service import PolicyService, to_public as policy_to_public

    service = PolicyService(db, ctx, provider)
    policy = await service.issue_from_proposal(proposal_id)
    await db.commit()
    return success_response(
        PolicyPublic.model_validate(policy_to_public(policy)).model_dump(mode="json"),
        message="Policy issued from proposal (pending payment)",
        request_id=getattr(request.state, "request_id", None),
        job_id=policy.job_id,
    )
