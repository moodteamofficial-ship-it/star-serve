"""Roles administration — tenant-scoped, soft-delete only, system roles protected."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import ResourceNotFoundError, ValidationAppError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.core.security.permissions import PLATFORM_WILDCARD, is_platform_only_permission
from app.modules.audit.service import AuditService
from app.modules.auth.service import AuthService
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.permissions_catalog import PERMISSION_CATALOG
from app.modules.roles.service import ensure_catalog_permissions

router = APIRouter(prefix="/roles", tags=["Roles"])


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")

    model_config = {"extra": "forbid"}


class RolePermissionsUpdateRequest(BaseModel):
    permission_codes: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=512)

    model_config = {"extra": "forbid"}


def _role_public(role: Role, permission_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": str(role.id),
        "tenant_id": str(role.tenant_id) if role.tenant_id else None,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "status": role.status,
        "permissions": permission_codes or [],
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


async def _load_role_permissions(db: AsyncSession, role_id: UUID) -> list[str]:
    rows = await db.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    )
    return list(rows.all())


async def _get_tenant_role(db: AsyncSession, ctx: SecurityContext, role_id: UUID) -> Role:
    role = await db.get(Role, role_id)
    if role is None or role.deleted_at is not None or role.status == "DELETED":
        raise ResourceNotFoundError("Role not found")
    if role.tenant_id is None:
        # Platform-global role — only platform admins
        if not ctx.is_platform_admin:
            raise ResourceNotFoundError("Role not found")
    elif role.tenant_id != ctx.tenant_id and not ctx.is_platform_admin:
        raise ResourceNotFoundError("Role not found")
    return role


@router.get("/permissions")
async def list_permission_catalog(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("role:manage"))],
) -> dict:
    # Keep the Roles board in lockstep with the catalog so new codes
    # (e.g. user:update) can be toggled per role immediately.
    if await ensure_catalog_permissions(db):
        await db.commit()
    catalog = {p["code"]: p for p in PERMISSION_CATALOG}
    rows = (await db.scalars(select(Permission).order_by(Permission.code))).all()
    items = []
    for row in rows:
        meta = catalog.get(row.code, {})
        # Agency admins never see platform:* — cannot assign what they cannot hold.
        if is_platform_only_permission(row.code) and not ctx.is_platform_admin:
            continue
        items.append(
            {
                "code": row.code,
                "description": row.description or meta.get("description"),
                "category": row.category or meta.get("category"),
            }
        )
    return success_response(
        {"items": items, "total": len(items)},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("")
async def list_roles(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("role:manage"))],
) -> dict:
    stmt = select(Role).where(Role.deleted_at.is_(None), Role.status != "DELETED")
    if ctx.is_platform_admin and ctx.role_code == "platform_admin":
        # Platform view: own tenant roles + global (null tenant) roles
        stmt = stmt.where(
            (Role.tenant_id == ctx.tenant_id) | (Role.tenant_id.is_(None))
        )
    else:
        stmt = stmt.where(Role.tenant_id == ctx.tenant_id)
    stmt = stmt.order_by(Role.is_system.desc(), Role.code)
    roles = (await db.scalars(stmt)).all()
    items = []
    for role in roles:
        perms = await _load_role_permissions(db, role.id)
        items.append(_role_public(role, perms))
    return success_response(
        {"items": items, "total": len(items)},
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{role_id}")
async def get_role(
    role_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("role:manage"))],
) -> dict:
    role = await _get_tenant_role(db, ctx, role_id)
    perms = await _load_role_permissions(db, role.id)
    return success_response(
        _role_public(role, perms),
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/{role_id}")
async def update_role(
    role_id: UUID,
    body: RoleUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("role:manage"))],
) -> dict:
    role = await _get_tenant_role(db, ctx, role_id)
    previous_status = role.status
    if body.name is not None:
        role.name = body.name.strip()
    if body.description is not None:
        role.description = body.description.strip() or None
    if body.status is not None:
        if role.is_system and body.status == "DISABLED" and role.code in {
            "agency_admin",
            "platform_admin",
        }:
            raise ValidationAppError("Cannot disable the primary administrator role")
        if (
            body.status == "DISABLED"
            and previous_status != "DISABLED"
            and role.id == ctx.role_id
        ):
            raise ValidationAppError(
                "You cannot disable the role you are currently signed in with"
            )
        role.status = body.status
    await AuditService(db).record(
        action="role.update",
        resource="role",
        resource_id=str(role.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"code": role.code, "status": role.status},
    )
    # Identity termination only — permission edits stay live without a re-login.
    if body.status == "DISABLED" and previous_status != "DISABLED":
        await AuthService(db).revoke_sessions_for_role(role.id, deleted_by=ctx.user_id)
    await db.commit()
    await db.refresh(role)
    perms = await _load_role_permissions(db, role.id)
    return success_response(
        _role_public(role, perms),
        message="Role updated",
        request_id=getattr(request.state, "request_id", None),
    )


@router.put("/{role_id}/permissions")
async def replace_role_permissions(
    role_id: UUID,
    body: RolePermissionsUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("role:manage"))],
) -> dict:
    role = await _get_tenant_role(db, ctx, role_id)
    codes = sorted({c.strip() for c in body.permission_codes if c.strip()})
    if not codes:
        raise ValidationAppError("At least one permission is required")

    for code in codes:
        if is_platform_only_permission(code) and not ctx.is_platform_admin:
            raise ValidationAppError("Cannot assign platform permissions")
        if code == PLATFORM_WILDCARD and role.code != "platform_admin":
            raise ValidationAppError("Wildcard permission is limited to the platform admin role")

    await ensure_catalog_permissions(db)
    perm_rows = (
        await db.scalars(select(Permission).where(Permission.code.in_(codes)))
    ).all()
    found = {p.code: p for p in perm_rows}
    missing = [c for c in codes if c not in found]
    if missing:
        raise ValidationAppError(f"Unknown permissions: {', '.join(missing)}")

    previous = await _load_role_permissions(db, role.id)
    await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    for code in codes:
        db.add(RolePermission(role_id=role.id, permission_id=found[code].id))
    await AuditService(db).record(
        action="role.permissions_replace",
        resource="role",
        resource_id=str(role.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        message=body.reason.strip(),
        metadata={"previous": previous, "next": codes, "role_code": role.code},
    )
    # Keep sessions. JWT is identity-only; every request already loads live
    # role_permissions, so a save must not force a logout. Clients refresh /me
    # and the next API call enforces the new grant set.
    await db.commit()
    return success_response(
        _role_public(role, codes),
        message="Role permissions updated",
        request_id=getattr(request.state, "request_id", None),
    )
