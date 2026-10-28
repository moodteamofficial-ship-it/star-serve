"""Audit HTTP routes — read-only."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.audit.query import AuditQueryService

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditEventPublic(BaseModel):
    id: str
    tenant_id: str | None
    user_id: str | None
    actor_name: str | None = None
    actor_email: str | None = None
    actor_avatar_url: str | None = None
    action: str
    resource: str
    resource_id: str | None
    result: str
    message: str | None
    metadata: dict
    request_id: str | None
    job_id: str | None
    correlation_id: str | None
    ip_address: str | None = None
    created_at: datetime

    model_config = {"extra": "forbid"}


@router.get("/events")
async def list_audit_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("audit:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    action: Annotated[str | None, Query(max_length=128)] = None,
    resource: Annotated[str | None, Query(max_length=128)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> dict:
    service = AuditQueryService(db, ctx)
    items, total = await service.list_public(
        page=page,
        limit=limit,
        action=action,
        resource=resource,
        query=q,
        since=since,
        until=until,
    )
    return success_response(
        {
            "items": [
                AuditEventPublic.model_validate(item).model_dump(mode="json") for item in items
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/events/{event_id}")
async def get_audit_event(
    event_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("audit:read"))],
) -> dict:
    service = AuditQueryService(db, ctx)
    item = await service.get_public(event_id)
    return success_response(
        AuditEventPublic.model_validate(item).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=item.get("job_id"),
    )
