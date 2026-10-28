"""Operational agency tenant for platform-home staff.

Guest quotes and most live issuance land on the insurance agency tenant.
Platform admins (and anyone authenticated to the platform tenant) manage that
work from the platform home tenant — remap list/settings context accordingly.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.context import SecurityContext


async def resolve_ops_tenant_id(session: AsyncSession, ctx: SecurityContext) -> UUID:
    """Return the tenant that owns guest/ops issuance for this principal."""
    from app.modules.insurance.guest_session import resolve_guest_tenant_id
    from app.modules.tenants.models import Tenant

    if ctx.is_guest:
        return ctx.tenant_id
    if ctx.is_platform_admin:
        return await resolve_guest_tenant_id(session)
    owner = await session.get(Tenant, ctx.tenant_id)
    if owner is not None and bool(owner.is_platform):
        return await resolve_guest_tenant_id(session)
    return ctx.tenant_id


async def with_ops_context(
    session: AsyncSession, ctx: SecurityContext
) -> SecurityContext:
    """Clone ctx bound to the operational agency when the actor is on platform."""
    home = await resolve_ops_tenant_id(session, ctx)
    if home == ctx.tenant_id:
        return ctx
    return replace(ctx, tenant_id=home)
