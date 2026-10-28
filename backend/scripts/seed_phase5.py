"""Ensure Phase 5 permissions exist and are attached to default roles."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.database.rls import set_rls_bypass
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.permissions_catalog import (
    AGENT_PERMISSIONS,
    FINANCE_PERMISSIONS,
    PERMISSION_CATALOG,
)

PHASE5_CODES = {
    "wallet:read",
    "wallet:topup",
    "wallet:debit",
    "certificate:read",
    "certificate:generate",
    "payment:reconcile",
}


async def ensure_phase5_permissions(session) -> None:
    existing = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for item in PERMISSION_CATALOG:
        if item["code"] not in existing:
            perm = Permission(
                id=uuid4(),
                code=item["code"],
                description=item.get("description"),
                category=item.get("category"),
            )
            session.add(perm)
            await session.flush()
            existing[item["code"]] = perm

    role_map = {
        "agency_admin": [c for c in PHASE5_CODES],
        "finance_officer": [c for c in FINANCE_PERMISSIONS if c in PHASE5_CODES],
        "agent": [c for c in AGENT_PERMISSIONS if c in PHASE5_CODES],
        "auditor": ["wallet:read", "certificate:read"],
        "branch_manager": [c for c in AGENT_PERMISSIONS if c in PHASE5_CODES],
    }

    for role_code, codes in role_map.items():
        roles = list((await session.scalars(select(Role).where(Role.code == role_code))).all())
        for role in roles:
            for code in codes:
                perm = existing.get(code)
                if not perm:
                    continue
                already = await session.scalar(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id,
                    )
                )
                if not already:
                    session.add(RolePermission(role_id=role.id, permission_id=perm.id))


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        # Domain and auth tables run FORCE RLS, which applies to the table owner too.
        await set_rls_bypass(session, True)
        await ensure_phase5_permissions(session)
        await session.commit()
        print("Phase 5 permissions ensured")


if __name__ == "__main__":
    asyncio.run(main())
