"""Explicit branch authorization scopes.

``NONE`` and ``ALL_TENANT`` must never share a representation. An empty
assignment set is not tenant-wide access.

``NULL`` branch_id is not an authorization state. Assigned-scope queries
must not treat unscoped rows as tenant-wide.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ValidationAppError


class BranchScope(StrEnum):
    NONE = "NONE"
    ASSIGNED = "ASSIGNED"
    ALL_TENANT = "ALL_TENANT"


TENANT_WIDE_BRANCH_PERMISSIONS: frozenset[str] = frozenset({"branch:all"})

_BRANCH_REQUIRED = "Select an authorized branch"
_BRANCH_UNAVAILABLE = "No authorized branch is available"


def resolve_branch_scope(
    *,
    is_platform_admin: bool,
    permissions: set[str],
    assigned_branch_ids: set[UUID],
) -> tuple[BranchScope, set[UUID]]:
    if is_platform_admin or bool(permissions & TENANT_WIDE_BRANCH_PERMISSIONS):
        return BranchScope.ALL_TENANT, set()
    if assigned_branch_ids:
        return BranchScope.ASSIGNED, set(assigned_branch_ids)
    return BranchScope.NONE, set()


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("Invalid branch") from exc


def apply_branch_predicate(stmt, model, ctx):
    """Restrict a tenant-scoped query to the caller's live branch set.

    ``NULL`` branch_id is never "all branches". Assigned principals see only
    explicit memberships. Models without ``branch_id`` are invisible to
    assigned/none scopes so aggregates cannot silently go tenant-wide.
    """
    from sqlalchemy import false

    if getattr(ctx, "is_guest", False) or getattr(ctx, "is_platform_admin", False):
        return stmt
    scope = getattr(ctx, "branch_scope", BranchScope.NONE)
    if scope == BranchScope.ALL_TENANT:
        return stmt
    branch_col = getattr(model, "branch_id", None)
    assigned = getattr(ctx, "branch_ids", set()) or set()
    if scope != BranchScope.ASSIGNED or not assigned or branch_col is None:
        return stmt.where(false())
    return stmt.where(branch_col.in_(assigned), branch_col.is_not(None))


def authorize_branch_access(ctx, resource_branch_id: UUID | None) -> None:
    """Fail closed unless the actor may see/mutate this branch-owned row.

    Historical ``branch_id IS NULL`` rows are visible only to tenant-wide
    principals. Assigned agents do not inherit them.
    """
    if getattr(ctx, "is_guest", False) or getattr(ctx, "is_platform_admin", False):
        return
    scope = getattr(ctx, "branch_scope", BranchScope.NONE)
    if scope == BranchScope.ALL_TENANT:
        return
    if scope != BranchScope.ASSIGNED:
        raise AuthorizationError()
    assigned = getattr(ctx, "branch_ids", set()) or set()
    if resource_branch_id is None or resource_branch_id not in assigned:
        raise AuthorizationError()


async def load_tenant_branch(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    branch_id: UUID,
):
    from app.modules.tenants.models import Branch

    stmt = select(Branch).where(
        Branch.id == branch_id,
        Branch.tenant_id == tenant_id,
        Branch.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def first_active_tenant_branch_id(
    session: AsyncSession,
    tenant_id: UUID,
) -> UUID | None:
    from app.modules.tenants.models import Branch

    return await session.scalar(
        select(Branch.id)
        .where(
            Branch.tenant_id == tenant_id,
            Branch.deleted_at.is_(None),
            Branch.status == "ACTIVE",
        )
        .order_by(Branch.created_at.asc())
        .limit(1)
    )


async def resolve_authorized_branch(
    ctx,
    session: AsyncSession,
    requested: UUID | str | None = None,
) -> UUID:
    """Derive a trusted branch for a new branch-owned record.

    Never returns NULL. Never trusts a client branch that is not live for
    this tenant and this principal.
    """
    wanted = _as_uuid(requested)
    tenant_id = ctx.tenant_id

    if getattr(ctx, "is_guest", False):
        if wanted is not None:
            row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=wanted)
            if row is None:
                raise ValidationAppError(_BRANCH_UNAVAILABLE)
            return wanted
        found = await first_active_tenant_branch_id(session, tenant_id)
        if found is None:
            raise ValidationAppError(_BRANCH_UNAVAILABLE)
        return found

    scope = getattr(ctx, "branch_scope", BranchScope.NONE)
    if scope == BranchScope.NONE and not getattr(ctx, "is_platform_admin", False):
        raise AuthorizationError(_BRANCH_UNAVAILABLE)

    async def _require_tenant_branch(branch_id: UUID) -> UUID:
        row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=branch_id)
        if row is None:
            raise ValidationAppError(_BRANCH_REQUIRED)
        return branch_id

    if scope == BranchScope.ALL_TENANT or getattr(ctx, "is_platform_admin", False):
        if wanted is not None:
            return await _require_tenant_branch(wanted)
        home = getattr(ctx, "home_branch_id", None)
        if home is not None:
            row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=home)
            if row is not None:
                return home
        found = await first_active_tenant_branch_id(session, tenant_id)
        if found is None:
            raise ValidationAppError(_BRANCH_UNAVAILABLE)
        return found

    assigned: set[UUID] = set(getattr(ctx, "branch_ids", set()) or set())
    if wanted is not None:
        if wanted not in assigned:
            raise AuthorizationError(_BRANCH_REQUIRED)
        return await _require_tenant_branch(wanted)
    if len(assigned) == 1:
        only = next(iter(assigned))
        return await _require_tenant_branch(only)
    home = getattr(ctx, "home_branch_id", None)
    if home is not None and home in assigned:
        return await _require_tenant_branch(home)
    if not assigned:
        raise AuthorizationError(_BRANCH_UNAVAILABLE)
    raise ValidationAppError(_BRANCH_REQUIRED)


async def resolve_transactional_branch(
    ctx,
    session: AsyncSession,
    preferred: UUID | str | None = None,
) -> UUID | None:
    """Attach a branch for OTP / kit / system mail about an existing resource.

    Prefer the resource's live branch. Never raise ``Select an authorized branch``
    — kits are not a branch-picker write path.
    """
    tenant_id = ctx.tenant_id
    wanted = _as_uuid(preferred)
    if wanted is not None:
        row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=wanted)
        if row is not None:
            return wanted

    home = getattr(ctx, "home_branch_id", None)
    if home is not None:
        row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=home)
        if row is not None:
            scope = getattr(ctx, "branch_scope", BranchScope.NONE)
            assigned: set[UUID] = set(getattr(ctx, "branch_ids", set()) or set())
            if (
                getattr(ctx, "is_platform_admin", False)
                or scope == BranchScope.ALL_TENANT
                or home in assigned
            ):
                return home

    scope = getattr(ctx, "branch_scope", BranchScope.NONE)
    if scope == BranchScope.ASSIGNED:
        for bid in getattr(ctx, "branch_ids", set()) or set():
            row = await load_tenant_branch(session, tenant_id=tenant_id, branch_id=bid)
            if row is not None:
                return bid

    return await first_active_tenant_branch_id(session, tenant_id)
