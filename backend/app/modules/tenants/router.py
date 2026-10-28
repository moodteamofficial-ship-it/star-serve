"""Tenant administration schemas and routes."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.dedicated import register_tenant_dedicated_dsn
from app.core.database.enums import DatabaseMode, TenantStatus, TenantType
from app.core.database.resolver import tenant_db_resolver
from app.core.dependencies.auth import get_current_context, get_db, require_permissions
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationAppError
from app.core.responses import success_response
from app.core.schemas import AppEmail
from app.core.security.context import SecurityContext
from app.core.security.crypto import (
    assert_dedicated_dsn_allowed,
    decrypt_secret,
    encrypt_secret,
    is_fernet_token,
)
from app.modules.audit.service import AuditService
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.permissions_catalog import PERMISSION_CATALOG, SYSTEM_ROLES
from app.modules.tenants.models import Tenant

router = APIRouter(prefix="/tenants", tags=["Tenants"])


class TenantCreateRequest(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    trading_name: str = Field(min_length=2, max_length=255)
    tenant_type: TenantType = TenantType.INSURANCE_AGENCY
    email: AppEmail | None = None
    phone: str | None = Field(default=None, max_length=64)
    registration_number: str | None = None
    kra_pin: str | None = Field(default=None, max_length=32)
    subscription_plan: str | None = None
    database_mode: DatabaseMode = DatabaseMode.SHARED_DATABASE

    model_config = {"extra": "forbid"}


class TenantPublic(BaseModel):
    id: str
    legal_name: str
    trading_name: str
    tenant_type: str
    status: str
    database_mode: str
    has_dedicated_dsn: bool = False
    dedicated_registered: bool = False
    email: str | None = None
    phone: str | None = None
    branding: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"extra": "forbid"}


class TenantStatusRequest(BaseModel):
    status: TenantStatus
    reason: str = Field(min_length=3, max_length=512)

    model_config = {"extra": "forbid"}


class TenantSettingsUpdateRequest(BaseModel):
    branding: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None
    trading_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: AppEmail | None = None
    phone: str | None = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class TenantDatabaseModeRequest(BaseModel):
    database_mode: DatabaseMode
    dedicated_database_dsn: str | None = Field(default=None, max_length=2048)
    reason: str = Field(min_length=3, max_length=512)

    model_config = {"extra": "forbid"}


def _to_public(tenant: Tenant) -> TenantPublic:
    return TenantPublic(
        id=str(tenant.id),
        legal_name=tenant.legal_name,
        trading_name=tenant.trading_name,
        tenant_type=tenant.tenant_type,
        status=tenant.status,
        database_mode=tenant.database_mode,
        has_dedicated_dsn=bool(tenant.dedicated_database_dsn),
        dedicated_registered=tenant_db_resolver.has_dedicated(tenant.id),
        email=tenant.email,
        phone=tenant.phone,
        branding=tenant.branding or {},
        configuration=tenant.configuration or {},
        created_at=tenant.created_at,
    )


async def _ensure_permissions(session: AsyncSession) -> dict[str, UUID]:
    existing = {p.code: p.id for p in (await session.scalars(select(Permission))).all()}
    for item in PERMISSION_CATALOG:
        if item["code"] not in existing:
            perm = Permission(
                code=item["code"],
                description=item.get("description"),
                category=item.get("category"),
            )
            session.add(perm)
            await session.flush()
            existing[item["code"]] = perm.id
    return existing


async def seed_tenant_roles(session: AsyncSession, tenant_id: UUID) -> dict[str, Role]:
    perm_map = await _ensure_permissions(session)
    roles: dict[str, Role] = {}
    for spec in SYSTEM_ROLES:
        code = str(spec["code"])
        role = await session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
        )
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                code=code,
                name=str(spec["name"]),
                is_system=True,
            )
            session.add(role)
            await session.flush()
        seen: set[str] = set()
        existing_perm_ids = set(
            (
                await session.scalars(
                    select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                )
            ).all()
        )
        for perm_code in spec["permissions"]:  # type: ignore[union-attr]
            code_s = str(perm_code)
            if code_s in seen:
                continue
            seen.add(code_s)
            pid = perm_map.get(code_s)
            if pid and pid not in existing_perm_ids:
                session.add(RolePermission(role_id=role.id, permission_id=pid))
        roles[code] = role
    return roles


@router.post("")
async def create_tenant(
    body: TenantCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:tenant:manage"))],
) -> dict:
    exists = await db.scalar(select(Tenant).where(Tenant.trading_name == body.trading_name))
    if exists:
        raise ConflictError("A tenant with this trading name already exists")

    tenant = Tenant(
        legal_name=body.legal_name,
        trading_name=body.trading_name,
        tenant_type=body.tenant_type.value,
        status=TenantStatus.PENDING.value,
        email=str(body.email) if body.email else None,
        phone=body.phone,
        registration_number=body.registration_number,
        kra_pin=body.kra_pin,
        subscription_plan=body.subscription_plan,
        database_mode=body.database_mode.value,
        configuration={},
        branding={},
        is_platform=False,
    )
    db.add(tenant)
    await db.flush()
    await seed_tenant_roles(db, tenant.id)
    from app.modules.claims.seed import seed_claim_governance

    await seed_claim_governance(db, tenant.id)
    await AuditService(db).record(
        action="tenant.create",
        resource="tenant",
        resource_id=str(tenant.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"new_tenant_id": str(tenant.id), "trading_name": tenant.trading_name},
    )
    await db.commit()
    await db.refresh(tenant)
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        message="Tenant created",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("")
async def list_tenants(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:tenant:manage"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    stmt = select(Tenant).where(Tenant.is_platform.is_(False))
    count_stmt = select(func.count()).select_from(Tenant).where(Tenant.is_platform.is_(False))
    if status:
        stmt = stmt.where(Tenant.status == status)
        count_stmt = count_stmt.where(Tenant.status == status)
    if q:
        like = f"%{q.strip()}%"
        filt = or_(Tenant.legal_name.ilike(like), Tenant.trading_name.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
    total = int(await db.scalar(count_stmt) or 0)
    rows = list(
        (
            await db.scalars(
                stmt.order_by(Tenant.created_at.desc()).offset((page - 1) * limit).limit(limit)
            )
        ).all()
    )
    return success_response(
        {
            "items": [_to_public(t).model_dump(mode="json") for t in rows],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/me")
async def my_tenant(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> dict:
    tenant = await db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise ResourceNotFoundError()
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/me/settings")
async def my_tenant_settings(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext, Depends(require_permissions("tenant:manage", "settings:manage"))
    ],
) -> dict:
    tenant = await db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise ResourceNotFoundError()
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/me")
async def update_my_tenant_settings(
    body: TenantSettingsUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext, Depends(require_permissions("tenant:manage", "settings:manage"))
    ],
) -> dict:
    tenant = await db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise ResourceNotFoundError()
    if body.branding is not None:
        tenant.branding = body.branding
    if body.configuration is not None:
        sanitized = {
            k: v
            for k, v in body.configuration.items()
            if k not in {"database_mode", "dedicated_database_dsn"}
        }
        tenant.configuration = sanitized
    if body.trading_name is not None:
        tenant.trading_name = body.trading_name
    if body.email is not None:
        tenant.email = str(body.email)
    if body.phone is not None:
        tenant.phone = body.phone
    await AuditService(db).record(
        action="tenant.settings_update",
        resource="tenant",
        resource_id=str(tenant.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    await db.commit()
    await db.refresh(tenant)
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        message="Tenant settings updated",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:tenant:manage"))],
) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.is_platform:
        raise ResourceNotFoundError()
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: UUID,
    body: TenantStatusRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:tenant:manage"))],
) -> dict:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.is_platform:
        raise ResourceNotFoundError()
    previous = tenant.status
    tenant.status = body.status.value
    await AuditService(db).record(
        action="tenant.status_change",
        resource="tenant",
        resource_id=str(tenant.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"from": previous, "to": body.status.value, "reason": body.reason},
    )
    await db.commit()
    return success_response(
        {"id": str(tenant.id), "status": tenant.status},
        message="Tenant status updated",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/{tenant_id}/database-mode")
async def update_tenant_database_mode(
    tenant_id: UUID,
    body: TenantDatabaseModeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:tenant:manage"))],
) -> dict:
    """Attach or detach dedicated DB config. DSN is never returned in responses."""
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.is_platform:
        raise ResourceNotFoundError()

    previous = tenant.database_mode
    mode = body.database_mode
    if mode == DatabaseMode.DEDICATED_DATABASE:
        submitted = (body.dedicated_database_dsn or "").strip()
        stored = tenant.dedicated_database_dsn
        if submitted:
            if not is_fernet_token(submitted):
                raise ValidationAppError(
                    "Dedicated DSN must be submitted as an encrypted envelope"
                )
            source = submitted
        else:
            source = stored
        if not source:
            raise ValidationAppError("dedicated_database_dsn is required for dedicated mode")
        try:
            plaintext = decrypt_secret(source, require_envelope=True) or ""
            plaintext = assert_dedicated_dsn_allowed(plaintext)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        tenant.dedicated_database_dsn = encrypt_secret(plaintext)
        tenant.database_mode = mode.value
        register_tenant_dedicated_dsn(tenant.id, plaintext)
    else:
        tenant.database_mode = DatabaseMode.SHARED_DATABASE.value
        tenant_db_resolver.unregister_dedicated(tenant.id)

    await AuditService(db).record(
        action="tenant.database_mode_change",
        resource="tenant",
        resource_id=str(tenant.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={
            "from": previous,
            "to": tenant.database_mode,
            "reason": body.reason,
            "has_dsn": bool(tenant.dedicated_database_dsn),
        },
    )
    await db.commit()
    await db.refresh(tenant)
    return success_response(
        _to_public(tenant).model_dump(mode="json"),
        message="Tenant database mode updated",
        request_id=getattr(request.state, "request_id", None),
    )
