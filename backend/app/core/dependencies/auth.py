"""FastAPI dependencies — DB session, auth context, permissions.

Identity comes from the access JWT; authorization permissions are always
resolved live from the role_permissions table on each request so revoked
rights cannot be exercised from a stale token.
"""

from collections.abc import AsyncGenerator
from typing import Annotated, Callable
from uuid import UUID
import json

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.database.enums import TenantStatus, UserStatus
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    SystemUnavailableError,
    TenantSuspendedError,
)
from app.core.security.branch_scope import BranchScope, resolve_branch_scope
from app.core.security.context import SecurityContext
from app.core.security.permissions import effective_permissions
from app.core.security.tokens import decode_access_token
from app.modules.roles.permissions_catalog import SALES_AGENT_ROLE_CODE
from app.modules.roles.service import ResolvedRole
from app.modules.system_config.service import SystemConfigService

PENDING_APPROVAL_MESSAGE = "Your account is awaiting approval. You can sign in once it is approved."

_AGENT_INTERMEDIARY_LOOKUP = text(
    """
    SELECT i.id
    FROM intermediaries i
    WHERE i.user_id = CAST(:uid AS uuid)
      AND i.tenant_id = CAST(:tid AS uuid)
      AND i.status = 'APPROVED'
      AND i.deleted_at IS NULL
    LIMIT 1
    """
)

# Identity stays resolvable while the operational switch is off so /me can
# refresh grants without treating a config change as a dead session.
_SESSION_KEEPALIVE_PATH_SUFFIXES = (
    "/auth/me",
    "/auth/preferred-env",
)


def _is_session_keepalive_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _SESSION_KEEPALIVE_PATH_SUFFIXES)


# One RTT: bind RLS, validate session/user/tenant, and load live role permissions.
# set_config() is text-only. Reusing :tid in a UUID comparison makes asyncpg/PG
# infer uuid and the whole statement dies — which also blocked the guest fallback.
_AUTH_BIND_AND_CHECK = text(
    """
    SELECT
      set_config('app.tenant_id', CAST(:tid AS text), true),
      set_config(
        'app.is_platform_admin',
        CASE WHEN EXISTS (
          SELECT 1
          FROM users lu
          WHERE lu.id = CAST(:uid AS uuid)
            AND lu.is_platform_admin IS TRUE
        ) THEN 'true' ELSE 'false' END,
        true
      ),
      set_config('app.user_id', CAST(:uid AS text), true),
      set_config('app.role_id', CAST(:rid AS text), true),
      set_config(
        'app.can_manage_users',
        CASE
          WHEN EXISTS (
            SELECT 1
            FROM users lu
            WHERE lu.id = CAST(:uid AS uuid)
              AND lu.is_platform_admin IS TRUE
          ) THEN 'true'
          WHEN EXISTS (
            SELECT 1
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            WHERE rp.role_id = CAST(:rid AS uuid)
              AND p.code IN (
                'user:manage',
                'user:write',
                'user:read',
                'user:create',
                'user:update',
                'user:disable',
                'role:manage'
              )
          ) THEN 'true'
          ELSE 'false'
        END,
        true
      ),
      set_config('app.allow_auth_write', 'false', true),
      set_config('app.allow_status_write', 'false', true),
      set_config('app.rls_bypass', 'false', true),
      (
        SELECT json_build_object(
          'ok', true,
          'revoked', s.revoked_at IS NOT NULL,
          'sess_deleted', s.deleted_at IS NOT NULL,
          'sess_status', s.status,
          'app_env', s.app_env,
          'role_id', s.role_id::text,
          'user_status', u.status,
          'user_deleted', u.deleted_at IS NOT NULL,
          'tenant_status', t.status,
          'user_ipa', u.is_platform_admin,
          'tenant_platform', t.is_platform,
          'branch_id', u.branch_id::text,
          'full_name', u.full_name
        )
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        JOIN tenants t ON t.id = u.tenant_id
        WHERE s.id = CAST(:sid AS uuid)
          AND u.id = CAST(:uid AS uuid)
          AND u.tenant_id = CAST(:tid AS uuid)
      ) AS auth_check,
      (
        SELECT json_build_object(
          'ok', true,
          'status', r.status,
          'deleted', r.deleted_at IS NOT NULL,
          'code', r.code,
          'name', r.name
        )
        FROM roles r
        WHERE r.id = CAST(:rid AS uuid)
      ) AS role_check,
      (
        SELECT coalesce(json_agg(p.code ORDER BY p.code), '[]'::json)
        FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = CAST(:rid AS uuid)
      ) AS live_perms,
      (
        SELECT coalesce(json_agg(ub.branch_id::text ORDER BY ub.branch_id::text), '[]'::json)
        FROM user_branches ub
        WHERE ub.user_id = CAST(:uid AS uuid)
      ) AS live_branches
    """
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SecurityContext:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError()

    payload = decode_access_token(token)
    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])
        tenant_id = UUID(payload["tid"])
        role_id = UUID(payload["rid"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthenticationError("Access token missing authz claims — please sign in again") from exc

    email = str(payload.get("email") or "")
    tenant_status = str(payload.get("ts") or "ACTIVE")

    row = (
        await db.execute(
            _AUTH_BIND_AND_CHECK,
            {
                "tid": str(tenant_id),
                "uid": str(user_id),
                "rid": str(role_id),
                "sid": str(session_id),
            },
        )
    ).one()
    check = row.auth_check
    if not check:
        raise AuthenticationError("Session is no longer valid")

    is_platform_admin = bool(check.get("user_ipa"))

    if check.get("revoked") or check.get("sess_deleted") or check.get("sess_status") in {
        "DELETED",
        "REVOKED",
    }:
        raise AuthenticationError("Session is no longer valid")
    if check.get("app_env") and check["app_env"] != settings.app_env:
        raise AuthenticationError("Session environment mismatch — please sign in again")
    if check.get("role_id") != str(role_id):
        raise AuthenticationError("Session role is no longer valid — please sign in again")
    if check.get("user_deleted") or check.get("user_status") in {
        UserStatus.DISABLED.value,
        UserStatus.DELETED.value,
        UserStatus.LOCKED.value,
    }:
        raise AuthenticationError("Invalid or disabled account")
    if check.get("user_status") == UserStatus.PENDING.value:
        raise AuthenticationError(PENDING_APPROVAL_MESSAGE)
    live_tenant_status = str(check.get("tenant_status") or tenant_status)
    if live_tenant_status in {
        TenantStatus.SUSPENDED.value,
        TenantStatus.DISABLED.value,
        TenantStatus.ARCHIVED.value,
    }:
        raise TenantSuspendedError()

    role_check = row.role_check
    if not role_check:
        raise AuthenticationError("Assigned role no longer exists")
    if role_check.get("deleted") or role_check.get("status") in {"DISABLED", "DELETED"}:
        raise AuthenticationError("Assigned role is disabled")

    role_code = str(role_check.get("code") or payload.get("rc") or "")
    role_name = str(role_check.get("name") or role_code)
    if not role_code:
        raise AuthenticationError("Access token missing role — please sign in again")

    raw_perms = row.live_perms or []
    if isinstance(raw_perms, str):
        raw_perms = json.loads(raw_perms)
    permissions = effective_permissions(
        is_platform_admin=is_platform_admin,
        permissions={str(p) for p in raw_perms if p},
    )
    if not permissions and not is_platform_admin:
        raise AuthorizationError("Role has no permissions configured")

    raw_branches = row.live_branches or []
    if isinstance(raw_branches, str):
        raw_branches = json.loads(raw_branches)
    assigned_branches: set[UUID] = set()
    for raw in raw_branches:
        try:
            assigned_branches.add(UUID(str(raw)))
        except ValueError:
            continue
    home_branch_id: UUID | None = None
    home_branch = check.get("branch_id")
    if home_branch:
        try:
            home_branch_id = UUID(str(home_branch))
            assigned_branches.add(home_branch_id)
        except ValueError:
            home_branch_id = None
    branch_scope, branch_ids = resolve_branch_scope(
        is_platform_admin=is_platform_admin,
        permissions=permissions,
        assigned_branch_ids=assigned_branches,
    )

    agent_intermediary_id: UUID | None = None
    if not is_platform_admin and role_code == SALES_AGENT_ROLE_CODE:
        agent_intermediary_id = await db.scalar(
            _AGENT_INTERMEDIARY_LOOKUP, {"uid": str(user_id), "tid": str(tenant_id)}
        )
        # Agent rows are filtered by intermediary, which is narrower than any branch.
        branch_scope, branch_ids = BranchScope.ALL_TENANT, set()

    ctx = SecurityContext(
        user_id=user_id,
        tenant_id=tenant_id,
        session_id=session_id,
        email=email,
        role_id=role_id,
        role_code=role_code,
        is_platform_admin=is_platform_admin,
        tenant_status=live_tenant_status,
        permissions=permissions,
        branch_scope=branch_scope,
        branch_ids=branch_ids,
        home_branch_id=home_branch_id,
        app_env=settings.app_env,
        actor_display_name=(str(check.get("full_name") or "").strip() or None),
        agent_intermediary_id=agent_intermediary_id,
    )
    ctx.bind()
    request.state.security_context = ctx
    request.state.resolved_role = ResolvedRole(
        role_id=role_id,
        code=role_code,
        name=role_name,
        tenant_id=tenant_id,
        permissions=frozenset(permissions),
    )

    # DB-backed master switch — platform admins retain break-glass access.
    # Session identity routes stay up so a config change never looks like logout.
    if not ctx.is_platform_admin and not _is_session_keepalive_path(request.url.path):
        operational = await SystemConfigService(db).get_operational()
        if not operational.enabled:
            raise SystemUnavailableError(
                operational.reason or "The platform is temporarily switched off"
            )

    return ctx


def require_permissions(*permissions: str) -> Callable[..., SecurityContext]:
    async def _dependency(
        ctx: Annotated[SecurityContext, Depends(get_current_context)],
    ) -> SecurityContext:
        ctx.require_staff_principal()
        ctx.require_any_permission(*permissions)
        return ctx

    return _dependency


async def get_optional_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SecurityContext | None:
    try:
        return await get_current_context(request, db)
    except (AuthenticationError, TenantSuspendedError, AuthorizationError):
        return None
