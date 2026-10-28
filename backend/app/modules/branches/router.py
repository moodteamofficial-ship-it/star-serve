"""Branch administration routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.branches.schemas import BranchCreateRequest, BranchPublic, BranchUpdateRequest
from app.modules.branches.service import BranchService

router = APIRouter(prefix="/branches", tags=["Branches"])


@router.get("")
async def list_branches(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("branch:manage"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
) -> dict:
    service = BranchService(db, ctx)
    items, total = await service.list_public(page=page, limit=limit, query=q)
    return success_response(
        {
            "items": [BranchPublic.model_validate(item).model_dump(mode="json") for item in items],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("")
async def create_branch(
    body: BranchCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("branch:manage"))],
) -> dict:
    service = BranchService(db, ctx)
    item = await service.create(body)
    await db.commit()
    return success_response(
        BranchPublic.model_validate(item).model_dump(mode="json"),
        message="Branch created",
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/{branch_id}")
async def update_branch(
    branch_id: UUID,
    body: BranchUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("branch:manage"))],
) -> dict:
    service = BranchService(db, ctx)
    item = await service.update(branch_id, body)
    await db.commit()
    return success_response(
        BranchPublic.model_validate(item).model_dump(mode="json"),
        message="Branch updated",
        request_id=getattr(request.state, "request_id", None),
    )
