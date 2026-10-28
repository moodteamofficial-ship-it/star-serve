"""Ensure Phase 6 notification permissions exist on default roles."""

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

PHASE6_CODES = {"notification:read", "notification:send"}


async def ensure_phase6_permissions(session) -> None:
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
        "agency_admin": list(PHASE6_CODES),
        "finance_officer": [c for c in FINANCE_PERMISSIONS if c in PHASE6_CODES],
        "agent": [c for c in AGENT_PERMISSIONS if c in PHASE6_CODES],
        "auditor": ["notification:read"],
        "branch_manager": [c for c in AGENT_PERMISSIONS if c in PHASE6_CODES]
        + ["notification:send"],
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
        await set_rls_bypass(session, True)
        await ensure_phase6_permissions(session)
        await session.commit()
        print("Phase 6 permissions ensured")


if __name__ == "__main__":
    asyncio.run(main())
