"""Policy HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.policies.schemas import PolicyCancelRequest, PolicyPublic
from app.modules.policies.service import PolicyService, to_public

router = APIRouter(prefix="/policies", tags=["Policies"])


def _provider() -> InsuranceProvider:
    return get_insurance_provider()


@router.get("")
async def list_policies(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = PolicyService(db, ctx, provider)
    rows, total = await service.list(page=page, limit=limit, query=q, status=status)
    return success_response(
        {
            "items": [
                PolicyPublic.model_validate(to_public(r)).model_dump(mode="json") for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{policy_id}")
async def get_policy(
    policy_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = PolicyService(db, ctx, provider)
    row = await service.get(policy_id)
    return success_response(
        PolicyPublic.model_validate(to_public(row)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.get("/{policy_id}/provider-details")
async def provider_details(
    policy_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = PolicyService(db, ctx, provider)
    data = await service.refresh_details(policy_id)
    await db.commit()
    return success_response(
        {
            "policy": PolicyPublic.model_validate(data["policy"]).model_dump(mode="json"),
            "provider": data["provider"],
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=data["policy"].get("job_id"),
    )


@router.post("/{policy_id}/activate")
async def activate_policy(
    policy_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:update"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = PolicyService(db, ctx, provider)
    row = await service.activate(policy_id)
    await db.commit()
    return success_response(
        PolicyPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Policy activated",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{policy_id}/cancel")
async def cancel_policy(
    policy_id: UUID,
    body: PolicyCancelRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("policy:cancel"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = PolicyService(db, ctx, provider)
    row = await service.cancel(policy_id, reason_code=body.reason_code, notes=body.notes)
    await db.commit()
    return success_response(
        PolicyPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Policy cancelled",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )
