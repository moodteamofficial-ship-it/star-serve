"""Bootstrap platform tenant, permissions, demo agencies, branches, and geo refs."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.database.enums import DatabaseMode, TenantStatus, TenantType, UserStatus
from app.core.database.rls import set_auth_write_gate, set_rls_bypass
from app.core.security.passwords import assert_password_strength
from app.modules.auth.service import AuthService
from app.modules.reference.models import Country
from app.modules.roles.models import Role, UserRole
from app.modules.roles.permissions_catalog import PERMISSION_CATALOG
from app.modules.tenants.models import Branch, Tenant
from app.modules.tenants.router import seed_tenant_roles, _ensure_permissions
from app.modules.users.models import User, UserBranch

KENYA_ID = UUID("a1000000-0000-4000-8000-000000000404")


def _seed_admin_password(*, required: bool) -> str | None:
    password = (os.environ.get("SEED_ADMIN_PASSWORD") or "").strip()
    if password:
        return assert_password_strength(password)
    if required:
        raise SystemExit(
            "SEED_ADMIN_PASSWORD is required. Refusing to seed accounts with a default password."
        )
    return None


async def _ensure_hq_branch(session, tenant: Tenant, kenya: Country) -> Branch:
    branch = await session.scalar(
        select(Branch).where(
            Branch.tenant_id == tenant.id,
            Branch.code == "HQ",
            Branch.deleted_at.is_(None),
        )
    )
    if branch is None:
        branch = Branch(
            tenant_id=tenant.id,
            name=f"{tenant.trading_name} HQ",
            code="HQ",
            status="ACTIVE",
            country_id=kenya.id,
            country_code=kenya.iso2,
            phone=kenya.phone_code,
            city="Nairobi",
            lat=Decimal("-1.286389"),
            lng=Decimal("36.817223"),
        )
        session.add(branch)
        await session.flush()
    return branch


async def _apply_user_geo(
    session,
    user: User,
    *,
    kenya: Country,
    branch: Branch | None,
) -> None:
    await set_auth_write_gate(session, allow_auth_write=True, allow_status_write=True)
    user.country_id = kenya.id
    user.country_code = kenya.iso2
    user.phone_country_code = kenya.phone_code
    user.currency = kenya.currency_code or "KES"
    if branch is not None:
        user.branch_id = branch.id
        existing = await session.scalar(
            select(UserBranch).where(
                UserBranch.user_id == user.id, UserBranch.branch_id == branch.id
            )
        )
        if existing is None:
            session.add(
                UserBranch(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    branch_id=branch.id,
                )
            )
    await set_auth_write_gate(session, allow_auth_write=False, allow_status_write=False)


async def _link_geo_and_branches(session) -> None:
    kenya = await session.get(Country, KENYA_ID)
    if kenya is None:
        kenya = await session.scalar(select(Country).where(Country.iso2 == "KE"))
    if kenya is None:
        print("WARNING: Kenya country row missing — run alembic upgrade head")
        return

    tenants = list(
        (
            await session.scalars(
                select(Tenant).where(Tenant.status == TenantStatus.ACTIVE.value)
            )
        ).all()
    )
    for tenant in tenants:
        branch = await _ensure_hq_branch(session, tenant, kenya)
        users = list(
            (
                await session.scalars(
                    select(User).where(
                        User.tenant_id == tenant.id,
                        User.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        for user in users:
            await _apply_user_geo(session, user, kenya=kenya, branch=branch)


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await set_rls_bypass(session, True)
        await set_auth_write_gate(session, allow_auth_write=True, allow_status_write=True)

        existing = await session.scalar(select(Tenant).where(Tenant.is_platform.is_(True)))
        if existing:
            await _ensure_permissions(session)
            from app.modules.roles.models import Permission, RolePermission

            perm_map = {
                p.code: p.id for p in (await session.scalars(select(Permission))).all()
            }
            platform_roles = list(
                (await session.scalars(select(Role).where(Role.code == "platform_admin"))).all()
            )
            for role in platform_roles:
                existing_ids = set(
                    (
                        await session.scalars(
                            select(RolePermission.permission_id).where(
                                RolePermission.role_id == role.id
                            )
                        )
                    ).all()
                )
                for item in PERMISSION_CATALOG:
                    pid = perm_map.get(item["code"])
                    if pid and pid not in existing_ids:
                        session.add(RolePermission(role_id=role.id, permission_id=pid))
            agencies = list(
                (await session.scalars(select(Tenant).where(Tenant.is_platform.is_(False)))).all()
            )
            for tenant in agencies:
                await seed_tenant_roles(session, tenant.id)

            auth = AuthService(session)
            users = (await session.scalars(select(User).where(User.role_id.is_(None)))).all()
            for user in users:
                ur = await session.scalar(select(UserRole).where(UserRole.user_id == user.id))
                if ur:
                    await set_auth_write_gate(session, allow_auth_write=True)
                    user.role_id = ur.role_id
                    await set_auth_write_gate(session, allow_auth_write=False)
            agency_a = await session.scalar(
                select(Tenant).where(Tenant.trading_name == "Agency A")
            )
            if agency_a:
                demo = await session.scalar(
                    select(User).where(User.email == "demo@agency-a.local")
                )
                if demo is None:
                    seed_password = _seed_admin_password(required=True)
                    agent_role = await session.scalar(
                        select(Role).where(
                            Role.tenant_id == agency_a.id, Role.code == "agent"
                        )
                    )
                    if agent_role is None:
                        roles = await seed_tenant_roles(session, agency_a.id)
                        agent_role = roles["agent"]
                    demo = await auth.register_user(
                        tenant_id=agency_a.id,
                        email="demo@agency-a.local",
                        password=seed_password,
                        full_name="Demo Agent",
                        status=UserStatus.ACTIVE.value,
                        role_id=agent_role.id,
                    )
                    await auth.assign_primary_role(
                        user=demo, role_id=agent_role.id, tenant_id=agency_a.id
                    )
                    print("Added demo agent: demo@agency-a.local")
            await _link_geo_and_branches(session)
            await session.commit()
            print("Platform exists — permissions refreshed; existing passwords left unchanged")
            return

        await _ensure_permissions(session)

        platform = Tenant(
            id=uuid4(),
            legal_name="Star Serve Platform",
            trading_name="Star Serve",
            tenant_type=TenantType.PLATFORM.value,
            status=TenantStatus.ACTIVE.value,
            database_mode=DatabaseMode.SHARED_DATABASE.value,
            configuration={},
            branding={"primaryColor": "#0B3D2E"},
            is_platform=True,
            email="platform@starserve.local",
        )
        session.add(platform)
        await session.flush()

        from app.modules.roles.models import Permission, RolePermission

        platform_role = Role(
            tenant_id=platform.id,
            code="platform_admin",
            name="Platform Administrator",
            is_system=True,
        )
        session.add(platform_role)
        await session.flush()
        perms = {
            p.code: p.id for p in (await session.scalars(select(Permission))).all()
        }
        for item in PERMISSION_CATALOG:
            session.add(
                RolePermission(role_id=platform_role.id, permission_id=perms[item["code"]])
            )

        auth = AuthService(session)
        seed_password = _seed_admin_password(required=True)
        platform_user = await auth.register_user(
            tenant_id=platform.id,
            email="admin@starserve.local",
            password=seed_password,
            full_name="Platform Admin",
            is_platform_admin=True,
            status=UserStatus.ACTIVE.value,
            role_id=platform_role.id,
        )
        await auth.assign_primary_role(
            user=platform_user, role_id=platform_role.id, tenant_id=platform.id
        )

        for name, email in (
            ("Agency A", "admin@agency-a.local"),
            ("Agency B", "admin@agency-b.local"),
        ):
            tenant = Tenant(
                id=uuid4(),
                legal_name=f"{name} Limited",
                trading_name=name,
                tenant_type=TenantType.INSURANCE_AGENCY.value,
                status=TenantStatus.ACTIVE.value,
                database_mode=DatabaseMode.SHARED_DATABASE.value,
                configuration={},
                branding={},
                is_platform=False,
                email=email,
            )
            session.add(tenant)
            await session.flush()
            roles = await seed_tenant_roles(session, tenant.id)
            user = await auth.register_user(
                tenant_id=tenant.id,
                email=email,
                password=seed_password,
                full_name=f"{name} Admin",
                status=UserStatus.ACTIVE.value,
                role_id=roles["agency_admin"].id,
            )
            await auth.assign_primary_role(
                user=user, role_id=roles["agency_admin"].id, tenant_id=tenant.id
            )

            if name == "Agency A":
                demo = await auth.register_user(
                    tenant_id=tenant.id,
                    email="demo@agency-a.local",
                    password=seed_password,
                    full_name="Demo Agent",
                    status=UserStatus.ACTIVE.value,
                    role_id=roles["agent"].id,
                )
                await auth.assign_primary_role(
                    user=demo, role_id=roles["agent"].id, tenant_id=tenant.id
                )

        await _link_geo_and_branches(session)
        await session.commit()
        print("Seed complete.")
        print("  Accounts created with SEED_ADMIN_PASSWORD (existing hashes are never rotated):")
        print("  platform: admin@starserve.local  (role: platform_admin)")
        print("  agency A: admin@agency-a.local  (role: agency_admin)")
        print("  demo:     demo@agency-a.local  (role: agent)")
        print("  agency B: admin@agency-b.local  (role: agency_admin)")
        print("  Next: python scripts/seed_phase2.py")


if __name__ == "__main__":
    asyncio.run(main())
