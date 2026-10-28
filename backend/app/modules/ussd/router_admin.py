"""Staff USSD administration — menus, simulator, analytics, sessions, provider."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import get_settings
from app.core.database.rls import set_rls_context
from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.ussd.analytics import funnel_metrics, overview_metrics, parse_period
from app.modules.ussd.engine import UssdEngine, ensure_published_config
from app.modules.ussd.enums import UssdProviderKind
from app.modules.ussd.service import UssdAdminService

router = APIRouter(prefix="/ussd/admin", tags=["USSD Admin"])


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


class DraftCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    from_published: bool = True


class ConfigUpdateRequest(BaseModel):
    name: str | None = None
    welcome_text: str | None = None
    definition: dict[str, Any] | None = None
    max_invalid_attempts: int | None = Field(default=None, ge=1, le=10)
    session_ttl_seconds: int | None = Field(default=None, ge=30, le=600)
    max_message_chars: int | None = Field(default=None, ge=80, le=500)
    nav_back: str | None = Field(default=None, max_length=8)
    nav_home: str | None = Field(default=None, max_length=8)
    nav_repeat: str | None = Field(default=None, max_length=8)
    notes: str | None = None

    model_config = {"extra": "forbid"}


class ProviderUpdateRequest(BaseModel):
    provider_kind: str | None = None
    service_code: str | None = None
    enabled: bool | None = None
    auth_header_name: str | None = None
    auth_secret: str | None = None
    allowed_ips: list[str] | None = None
    protocol_options: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class SimulatorRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)
    msisdn: str = Field(min_length=9, max_length=20)
    text: str | None = Field(default=None, max_length=256)
    service_code: str | None = Field(default=None, max_length=32)
    idempotency_key: str | None = Field(default=None, max_length=128)
    restart: bool = False

    model_config = {"extra": "forbid"}


@router.get("/overview")
async def ussd_overview(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
    period: Annotated[str | None, Query()] = "last_7_days",
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    include_test: Annotated[bool, Query()] = False,
) -> dict:
    await set_rls_context(db, tenant_id=ctx.tenant_id, is_platform_admin=False)
    service = UssdAdminService(db, ctx)
    published = await service.get_published()
    if published is None:
        published = await ensure_published_config(db, ctx.tenant_id)
        await db.commit()
    provider = await service.get_or_create_provider()
    await db.commit()
    start_dt, end_dt = parse_period(period, start, end)
    metrics = await overview_metrics(
        db,
        tenant_id=ctx.tenant_id,
        start=start_dt,
        end=end_dt,
        include_test=include_test,
    )
    return success_response(
        {
            "health": {
                "service": "ok",
                "published_version": published.version if published else None,
                "provider_kind": provider.provider_kind,
                "provider_enabled": provider.enabled,
                "callback_path": provider.callback_path,
                "callback_url": service.public_callback_url(provider.callback_path),
                "service_code": provider.service_code,
            },
            "metrics": metrics,
        },
        request_id=_rid(request),
    )


@router.get("/configs")
async def list_configs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    rows = await service.list_configs()
    if not rows:
        row = await ensure_published_config(db, ctx.tenant_id)
        await db.commit()
        rows = [row]
    return success_response(
        {"items": [service.config_public(r) for r in rows]},
        request_id=_rid(request),
    )


@router.post("/configs")
async def create_draft(
    body: DraftCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:manage"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.create_draft(name=body.name, from_published=body.from_published)
    await db.commit()
    return success_response(service.config_public(row), request_id=_rid(request))


@router.get("/configs/{config_id}")
async def get_config(
    config_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.get_config(config_id)
    return success_response(service.config_public(row), request_id=_rid(request))


@router.patch("/configs/{config_id}")
async def update_config(
    config_id: UUID,
    body: ConfigUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:manage"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.update_draft(config_id, body.model_dump(exclude_unset=True))
    await db.commit()
    return success_response(service.config_public(row), request_id=_rid(request))


@router.post("/configs/{config_id}/publish")
async def publish_config(
    config_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:manage"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.publish(config_id)
    await db.commit()
    return success_response(service.config_public(row), message="Menu published", request_id=_rid(request))


@router.get("/provider")
async def get_provider(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.get_or_create_provider()
    await db.commit()
    return success_response(service.provider_public(row), request_id=_rid(request))


@router.put("/provider")
async def update_provider(
    body: ProviderUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:manage"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    row = await service.update_provider(body.model_dump(exclude_unset=True))
    await db.commit()
    return success_response(service.provider_public(row), request_id=_rid(request))


@router.post("/simulator")
async def run_simulator(
    body: SimulatorRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:manage"))],
) -> dict:
    """Interactive phone simulator — same engine as the live callback, test telemetry only."""
    await set_rls_context(db, tenant_id=ctx.tenant_id, is_platform_admin=False)
    await ensure_published_config(db, ctx.tenant_id)
    session_id = body.session_id or f"sim-{uuid4().hex[:16]}"
    if body.restart:
        session_id = f"sim-{uuid4().hex[:16]}"
    engine = UssdEngine()
    result = await engine.handle(
        db,
        tenant_id=ctx.tenant_id,
        provider_kind=UssdProviderKind.SIMULATOR.value,
        provider_session_id=session_id,
        service_code=body.service_code or get_settings().ussd_default_service_code,
        msisdn=body.msisdn,
        text=None if body.restart else body.text,
        correlation_id=getattr(request.state, "request_id", None) or str(uuid4()),
        is_test=True,
        idempotency_key=body.idempotency_key,
    )
    await db.commit()
    return success_response(
        {
            "session_id": session_id,
            "ussd_session_id": str(result.session_id) if result.session_id else None,
            "text": result.text,
            "response_type": result.response_type,
            "test_mode": True,
        },
        request_id=_rid(request),
    )


@router.get("/analytics")
async def analytics(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:analytics"))],
    period: Annotated[str | None, Query()] = "last_7_days",
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    workflow: Annotated[str | None, Query()] = None,
    include_test: Annotated[bool, Query()] = False,
) -> dict:
    start_dt, end_dt = parse_period(period, start, end)
    overview = await overview_metrics(
        db,
        tenant_id=ctx.tenant_id,
        start=start_dt,
        end=end_dt,
        include_test=include_test,
    )
    funnel = None
    if workflow:
        funnel = await funnel_metrics(
            db,
            tenant_id=ctx.tenant_id,
            workflow=workflow,
            start=start_dt,
            end=end_dt,
            include_test=include_test,
        )
    return success_response(
        {"overview": overview, "funnel": funnel},
        request_id=_rid(request),
    )


@router.get("/sessions")
async def list_sessions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_test: Annotated[bool, Query()] = True,
) -> dict:
    service = UssdAdminService(db, ctx)
    items = await service.list_sessions(limit=limit, include_test=include_test)
    return success_response({"items": items}, request_id=_rid(request))


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
) -> dict:
    service = UssdAdminService(db, ctx)
    data = await service.get_session(session_id)
    return success_response(data, request_id=_rid(request))


@router.get("/audit")
async def list_audit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("ussd:read"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    service = UssdAdminService(db, ctx)
    items = await service.list_audit(limit=limit)
    return success_response({"items": items}, request_id=_rid(request))
