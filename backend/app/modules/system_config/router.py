"""System configuration HTTP API — platform admins only for mutations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.system_config.schemas import (
    NotificationChannelsUpdateRequest,
    OperationalUpdateRequest,
    ServicesUpdateRequest,
)
from app.modules.system_config.service import SystemConfigService

router = APIRouter(prefix="/system-config", tags=["System configuration"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


@router.get("")
async def get_system_config(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    snap = await SystemConfigService(db).snapshot()
    return success_response(
        snap.model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/operational")
async def get_operational(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    state = await SystemConfigService(db).get_operational()
    return success_response(
        state.model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/operational")
async def put_operational(
    body: OperationalUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    ip, ua = _client_meta(request)
    state = await SystemConfigService(db).set_operational(
        enabled=body.enabled,
        reason=body.reason.strip(),
        expected_version=body.expected_version,
        actor_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        ip_address=ip,
        user_agent=ua,
    )
    await db.commit()
    return success_response(
        state.model_dump(mode="json"),
        message="System operational state updated",
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/services")
async def put_services(
    body: ServicesUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    ip, ua = _client_meta(request)
    state = await SystemConfigService(db).set_services(
        services=body.services,
        reason=body.reason.strip(),
        expected_version=body.expected_version,
        actor_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        ip_address=ip,
        user_agent=ua,
    )
    await db.commit()
    return success_response(
        state.model_dump(mode="json"),
        message="System services updated",
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/notification-channels")
async def put_notification_channels(
    body: NotificationChannelsUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("platform:config:manage", "platform:tenant:manage")),
    ],
) -> dict:
    ip, ua = _client_meta(request)
    state = await SystemConfigService(db).set_notification_channels(
        channels=body.channels,
        reason=body.reason.strip(),
        expected_version=body.expected_version,
        actor_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        ip_address=ip,
        user_agent=ua,
    )
    await db.commit()
    return success_response(
        state.model_dump(mode="json"),
        message="Notification channels updated",
        request_id=getattr(request.state, "request_id", None),
    )
