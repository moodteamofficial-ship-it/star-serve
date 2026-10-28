"""Intermediary HTTP routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.intermediaries.models import Intermediary
from app.modules.intermediaries.schemas import (
    IntermediaryCreateRequest,
    IntermediaryLoginRequest,
    IntermediaryPublic,
    IntermediaryResendKitRequest,
    IntermediaryUpdateRequest,
)
from app.modules.intermediaries.service import IntermediaryService, to_public

router = APIRouter(prefix="/intermediaries", tags=["Intermediaries"])


async def _public(service: IntermediaryService, row: Intermediary) -> dict:
    statuses = await service.login_statuses([row])
    return IntermediaryPublic.model_validate(
        to_public(row, login_status=statuses.get(row.id))
    ).model_dump(mode="json")


@router.post("")
async def create_intermediary(
    body: IntermediaryCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:create"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    row = await service.create(body)
    data = await _public(service, row)
    await db.commit()
    return success_response(
        data,
        message="Intermediary created",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("")
async def list_intermediaries(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = IntermediaryService(db, ctx)
    rows, total = await service.list(page=page, limit=limit, query=q, status=status)
    statuses = await service.login_statuses(rows)
    return success_response(
        {
            "items": [
                IntermediaryPublic.model_validate(
                    to_public(r, login_status=statuses.get(r.id))
                ).model_dump(mode="json")
                for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{intermediary_id}")
async def get_intermediary(
    intermediary_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:read"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    row = await service.get(intermediary_id)
    return success_response(
        await _public(service, row),
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.patch("/{intermediary_id}")
async def update_intermediary(
    intermediary_id: UUID,
    body: IntermediaryUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:create"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    row = await service.update(intermediary_id, body)
    data = await _public(service, row)
    await db.commit()
    return success_response(
        data,
        message="Intermediary updated",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{intermediary_id}/login")
async def set_intermediary_login(
    intermediary_id: UUID,
    body: IntermediaryLoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:create"))],
) -> dict:
    """Create the agent's sign-in, or reset its password."""
    service = IntermediaryService(db, ctx)
    row = await service.set_login(intermediary_id, body.password)
    data = await _public(service, row)
    await db.commit()
    return success_response(
        data,
        message="Agent login saved",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{intermediary_id}/kit-channels")
async def list_agent_kit_channels(
    intermediary_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:read"))],
) -> dict:
    """Enabled channels that can receive this agent's QR kit (email / SMS / WhatsApp)."""
    service = IntermediaryService(db, ctx)
    channels = await service.kit_channels(intermediary_id)
    return success_response(
        {"channels": channels},
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{intermediary_id}/resend-kit")
async def resend_agent_kit(
    intermediary_id: UUID,
    body: IntermediaryResendKitRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:create"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    data = await service.resend_kit(intermediary_id, body.channel)
    await db.commit()
    label = {"EMAIL": "Email", "SMS": "SMS", "WHATSAPP": "WhatsApp"}.get(
        body.channel, body.channel.title()
    )
    return success_response(
        data,
        message=f"Agent kit queued via {label}",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{intermediary_id}/approve")
async def approve_intermediary(
    intermediary_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:approve"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    row = await service.approve(intermediary_id)
    data = await _public(service, row)
    await db.commit()
    return success_response(
        data,
        message="Intermediary approved",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{intermediary_id}/suspend")
async def suspend_intermediary(
    intermediary_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:approve"))],
) -> dict:
    service = IntermediaryService(db, ctx)
    row = await service.suspend(intermediary_id)
    data = await _public(service, row)
    await db.commit()
    return success_response(
        data,
        message="Intermediary suspended",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )
