"""Notification HTTP routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.notifications.schemas import NotificationPublic, NotificationSendRequest
from app.modules.notifications.service import NotificationService, enrich_public, to_public

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/templates")
async def list_templates(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:read"))],
) -> dict:
    service = NotificationService(db, ctx)
    return success_response(
        {"items": service.templates()},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("")
async def list_notifications(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
    channel: Annotated[str | None, Query(max_length=16)] = None,
) -> dict:
    service = NotificationService(db, ctx)
    rows, total = await service.list(
        page=page, limit=limit, query=q, status=status, channel=channel
    )
    items = await enrich_public(db, ctx, rows)
    return success_response(
        {
            "items": [
                NotificationPublic.model_validate(item).model_dump(mode="json") for item in items
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{notification_id}")
async def get_notification(
    notification_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:read"))],
) -> dict:
    service = NotificationService(db, ctx)
    row = await service.get(notification_id)
    item = (await enrich_public(db, ctx, [row]))[0]
    return success_response(
        NotificationPublic.model_validate(item).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("")
async def send_notification(
    body: NotificationSendRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:send"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    service = NotificationService(db, ctx)
    result = await service.send(body, idempotency_key=idempotency_key)
    await db.commit()
    if isinstance(result, dict):
        data: dict[str, Any] = result
        job_id = data.get("job_id")
    else:
        data = NotificationPublic.model_validate(to_public(result)).model_dump(mode="json")
        job_id = result.job_id
    return success_response(
        data,
        message="Notification queued",
        request_id=getattr(request.state, "request_id", None),
        job_id=job_id,
    )


@router.post("/{notification_id}/retry")
async def retry_notification(
    notification_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:send"))],
) -> dict:
    service = NotificationService(db, ctx)
    row = await service.deliver(notification_id)
    await db.commit()
    return success_response(
        NotificationPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Delivery attempted",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{notification_id}/cancel")
async def cancel_notification(
    notification_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("notification:send"))],
) -> dict:
    service = NotificationService(db, ctx)
    row = await service.cancel(notification_id)
    await db.commit()
    return success_response(
        NotificationPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Notification cancelled",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )
