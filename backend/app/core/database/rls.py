"""Apply PostgreSQL RLS session variables for defense in depth.

Auth tables use FORCE RLS. Unauthenticated identity lookups briefly set
app.rls_bypass; normal requests set tenant/user/role context instead.
Never expose these settings to clients.

All app.* flags are applied in a single round-trip (critical over remote
Supabase / Cloud SQL latency).
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# One SELECT with many set_config() calls = one network RTT.
_SET_RLS_CONTEXT = text(
    """
    SELECT
      set_config('app.tenant_id', CAST(:tid AS text), true),
      set_config('app.is_platform_admin', CAST(:is_admin AS text), true),
      set_config('app.user_id', CAST(:uid AS text), true),
      set_config('app.role_id', CAST(:rid AS text), true),
      set_config('app.can_manage_users', CAST(:can_manage AS text), true),
      set_config('app.allow_auth_write', CAST(:allow_auth AS text), true),
      set_config('app.allow_status_write', CAST(:allow_status AS text), true),
      set_config('app.rls_bypass', CAST(:bypass AS text), true)
    """
)

_SET_RLS_BYPASS = text("SELECT set_config('app.rls_bypass', :flag, true)")

_SET_AUTH_WRITE_GATE = text(
    """
    SELECT
      set_config('app.allow_auth_write', :allow_auth, true),
      set_config('app.allow_status_write', :allow_status, true)
    """
)


def _flag(value: bool) -> str:
    return "true" if value else "false"


async def set_rls_context(
    session: AsyncSession,
    *,
    tenant_id: UUID | None,
    is_platform_admin: bool = False,
    user_id: UUID | None = None,
    role_id: UUID | None = None,
    can_manage_users: bool = False,
    allow_auth_write: bool = False,
    allow_status_write: bool = False,
    rls_bypass: bool = False,
) -> None:
    """SET LOCAL so RLS policies and auth triggers can read app.* for this transaction."""
    await session.execute(
        _SET_RLS_CONTEXT,
        {
            "tid": str(tenant_id) if tenant_id else "",
            "is_admin": _flag(is_platform_admin),
            "uid": str(user_id) if user_id else "",
            "rid": str(role_id) if role_id else "",
            "can_manage": _flag(can_manage_users),
            "allow_auth": _flag(allow_auth_write),
            "allow_status": _flag(allow_status_write),
            "bypass": _flag(rls_bypass),
        },
    )


async def set_rls_bypass(session: AsyncSession, enabled: bool) -> None:
    await session.execute(_SET_RLS_BYPASS, {"flag": _flag(enabled)})


async def set_auth_write_gate(
    session: AsyncSession,
    *,
    allow_auth_write: bool = False,
    allow_status_write: bool = False,
) -> None:
    await session.execute(
        _SET_AUTH_WRITE_GATE,
        {
            "allow_auth": _flag(allow_auth_write),
            "allow_status": _flag(allow_status_write),
        },
    )
