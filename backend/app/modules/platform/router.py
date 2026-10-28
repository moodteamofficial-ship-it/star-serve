"""Platform metrics — coarse counts only, no PII."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import TenantStatus
from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.customers.models import Customer
from app.modules.payments.models import Payment
from app.modules.policies.models import Policy
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

router = APIRouter(prefix="/platform", tags=["Platform"])


@router.get("/metrics")
async def platform_metrics(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("platform:metrics:read"))],
) -> dict:
    tenants_total = int(await db.scalar(select(func.count()).select_from(Tenant)) or 0)
    tenants_active = int(
        await db.scalar(
            select(func.count())
            .select_from(Tenant)
            .where(Tenant.status == TenantStatus.ACTIVE.value)
        )
        or 0
    )
    tenants_dedicated = int(
        await db.scalar(
            select(func.count())
            .select_from(Tenant)
            .where(Tenant.database_mode == "DEDICATED_DATABASE")
        )
        or 0
    )
    users_total = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    policies_total = int(await db.scalar(select(func.count()).select_from(Policy)) or 0)
    payments_total = int(await db.scalar(select(func.count()).select_from(Payment)) or 0)
    customers_total = int(
        await db.scalar(
            select(func.count()).select_from(Customer).where(Customer.deleted_at.is_(None))
        )
        or 0
    )
    return success_response(
        {
            "tenants": {
                "total": tenants_total,
                "active": tenants_active,
                "dedicated_database": tenants_dedicated,
            },
            "users": {"total": users_total},
            "policies": {"total": policies_total},
            "payments": {"total": payments_total},
            "customers": {"total": customers_total},
        },
        request_id=getattr(request.state, "request_id", None),
    )
