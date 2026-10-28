"""Seed platform insurance reference catalog (Phase 2)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.database.rls import set_rls_bypass
from app.modules.products.models import CancellationReason, InsuranceProduct, VehicleMake
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.permissions_catalog import PERMISSION_CATALOG
from app.modules.tenants.models import Tenant


PLATFORM_PRODUCTS = [
    {
        "code": "MOTOR_COMP",
        "name": "Motor Comprehensive",
        "description": "Comprehensive motor cover",
        "cover_options": ["Comprehensive", "Third Party Fire & Theft", "Third Party Only"],
    },
    {
        "code": "MOTOR_TPO",
        "name": "Motor Third Party Only",
        "description": "Third party liability motor cover",
        "cover_options": ["Third Party Only"],
    },
    {
        "code": "COMMERCIAL_MOTOR",
        "name": "Commercial Motor",
        "description": "Commercial vehicle cover",
        "cover_options": ["Comprehensive", "Third Party Only"],
    },
]

PLATFORM_MAKES = [
    ("TOYOTA", "Toyota", 10),
    ("NISSAN", "Nissan", 20),
    ("MITSUBISHI", "Mitsubishi", 30),
    ("ISUZU", "Isuzu", 40),
    ("MAZDA", "Mazda", 50),
    ("SUBARU", "Subaru", 60),
    ("HONDA", "Honda", 70),
    ("MERCEDES", "Mercedes-Benz", 80),
    ("BMW", "BMW", 90),
    ("VW", "Volkswagen", 100),
]

PLATFORM_REASONS = [
    ("SOLD", "Vehicle sold"),
    ("TOTAL_LOSS", "Total loss"),
    ("INSURED_REQUEST", "Insured request"),
    ("NON_PAYMENT", "Non-payment of premium"),
    ("DUPLICATE", "Duplicate cover"),
]


async def ensure_new_permissions(session) -> None:
    existing = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    created_ids: list = []
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
            created_ids.append(perm.id)

    if not created_ids:
        return

    # Attach newly added non-platform permissions to agency_admin roles
    new_codes = {
        item["code"]
        for item in PERMISSION_CATALOG
        if item["code"] in {"agent:read", "product:read", "product:manage"}
    }
    admin_roles = list(
        (await session.scalars(select(Role).where(Role.code == "agency_admin"))).all()
    )
    for role in admin_roles:
        for code in new_codes:
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

    # Platform admin role gets everything
    platform_roles = list(
        (await session.scalars(select(Role).where(Role.code == "platform_admin"))).all()
    )
    for role in platform_roles:
        for perm in existing.values():
            already = await session.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            )
            if not already:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))


async def seed_reference_data(session) -> None:
    existing_product = await session.scalar(
        select(InsuranceProduct).where(
            InsuranceProduct.tenant_id.is_(None),
            InsuranceProduct.code == "MOTOR_COMP",
        )
    )
    if existing_product:
        return

    for item in PLATFORM_PRODUCTS:
        session.add(
            InsuranceProduct(
                id=uuid4(),
                tenant_id=None,
                code=item["code"],
                name=item["name"],
                description=item["description"],
                cover_options=item["cover_options"],
                is_active=True,
                provider_code="LOCAL",
                metadata_json={"source": "phase2_seed"},
            )
        )
    for code, name, order in PLATFORM_MAKES:
        session.add(
            VehicleMake(
                id=uuid4(),
                tenant_id=None,
                code=code,
                name=name,
                sort_order=order,
                is_active=True,
                provider_code="LOCAL",
            )
        )
    for code, label in PLATFORM_REASONS:
        session.add(
            CancellationReason(
                id=uuid4(),
                tenant_id=None,
                code=code,
                label=label,
                is_active=True,
                provider_code="LOCAL",
            )
        )


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await set_rls_bypass(session, True)
        tenants = list((await session.scalars(select(Tenant))).all())
        if not tenants:
            print("No tenants found — run seed_phase1.py first")
            return
        await ensure_new_permissions(session)
        await seed_reference_data(session)
        await session.commit()
        print("Phase 2 reference data + permissions seeded")


if __name__ == "__main__":
    asyncio.run(main())
