"""Insurance provider orchestration routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.redis_client import get_redis_client
from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import AuthorizationError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.insurance.issuance_schemas import (
    IssuanceClientRequest,
    IssuancePayCancelRequest,
    IssuancePayRequest,
    IssuanceSubmitRequest,
)
from app.modules.insurance.issuance_service import IssuanceService
from app.modules.insurance.schemas import (
    EnsureClientRequest,
    EnsureIntermediaryRequest,
    PremiumCalculateRequest,
    PremiumPublic,
)
from app.modules.insurance.service import InsuranceOrchestrationService
from app.modules.products.cache import ReferenceDataCache

router = APIRouter(prefix="/insurance", tags=["Insurance"])


def get_provider() -> InsuranceProvider:
    return get_insurance_provider()


@router.get("/provider-wallet/balance")
async def provider_wallet_balance(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("wallet:read"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
    agent_code: Annotated[str | None, Query(max_length=64)] = None,
) -> dict:
    """Definite agent wallet / float balance (separate from StarServe agency wallet)."""
    from app.core.config import get_settings
    from app.core.exceptions import ValidationAppError

    settings = get_settings()
    configured = (settings.definite_assurance_agent_code or "").strip()
    if ctx.is_platform_admin and (agent_code or "").strip():
        code = agent_code.strip()
    else:
        code = configured
    if not code:
        raise ValidationAppError("Agent code is not configured")

    result = await provider.check_wallet_balance(agent_code=code)
    from app.modules.audit.service import AuditService

    await AuditService(db).record(
        action="insurance.provider_wallet_balance",
        resource="provider_wallet",
        resource_id=code,
        tenant_id=ctx.tenant_id,
        user_id=ctx.actor_user_id,
        metadata={
            "agent_code": code,
            "balance": result.get("balance") if isinstance(result, dict) else None,
        },
    )
    await db.commit()
    return success_response(
        {
            "agent_code": code,
            "balance": result.get("balance") if isinstance(result, dict) else None,
            "currency": (result.get("currency") if isinstance(result, dict) else None) or "KES",
            "source": result.get("source") if isinstance(result, dict) else None,
        },
        message="Provider wallet balance loaded",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/clients/check")
async def check_client(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:read"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
    id_number: Annotated[str, Query(min_length=5, max_length=32)],
) -> dict:
    if ctx.is_sales_agent:
        raise AuthorizationError()
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.check_client(id_number)
    await db.commit()
    return success_response(
        data,
        message="Client check completed",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/clients/ensure")
async def ensure_client(
    body: EnsureClientRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("customer:create"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.ensure_client(body)
    await db.commit()
    return success_response(
        data,
        message="Client ensured with provider and local tenant record",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.get("/intermediaries/check")
async def check_intermediary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:read"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
    identification: Annotated[str, Query(min_length=5, max_length=64)],
) -> dict:
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.check_intermediary(identification)
    await db.commit()
    return success_response(
        data,
        message="Intermediary check completed",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/intermediaries/ensure")
async def ensure_intermediary(
    body: EnsureIntermediaryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("agent:create"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.ensure_intermediary(body)
    await db.commit()
    return success_response(
        data,
        message="Intermediary ensured with provider and local tenant record",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.get("/catalog")
async def insurance_catalog(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:read"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    """Catalog for the authenticated staff quote wizard."""
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.get_catalog()
    return success_response(
        data,
        message="Insurance catalog loaded",
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/premium/calculate")
async def calculate_premium(
    body: PremiumCalculateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("proposal:create")),
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.calculate_premium(body)
    await db.commit()
    return success_response(
        {
            "job_id": data["job_id"],
            "premium": PremiumPublic.model_validate(data["premium"]).model_dump(),
        },
        message="Premium calculated from insurance provider",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/reference/sync")
async def sync_reference(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("product:manage"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = InsuranceOrchestrationService(
        db, ctx, provider, ReferenceDataCache(get_redis_client())
    )
    data = await service.sync_reference_data()
    await db.commit()
    return success_response(
        data,
        message="Reference data synced from insurance provider",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/issuance/client")
async def issuance_client(
    body: IssuanceClientRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("customer:create", "proposal:create")),
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = IssuanceService(db, ctx, provider, ReferenceDataCache(get_redis_client()))
    data = await service.ensure_client(body)
    await db.commit()
    return success_response(
        data,
        message="Client ready for issuance",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/issuance/submit")
async def issuance_submit(
    body: IssuanceSubmitRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("proposal:create", "policy:create")),
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = IssuanceService(db, ctx, provider, ReferenceDataCache(get_redis_client()))
    data = await service.submit(body)
    await db.commit()
    return success_response(
        data,
        message="Proposal submitted and policy awaiting payment",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/issuance/pay/cancel")
async def issuance_pay_cancel(
    body: IssuancePayCancelRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:create"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = IssuanceService(db, ctx, provider, ReferenceDataCache(get_redis_client()))
    data = await service.cancel_pending_payment(body.policy_id)
    await db.commit()
    return success_response(
        data,
        message="Payment cancelled" if data["cancelled"] else "Nothing to cancel",
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/issuance/pay")
async def issuance_pay(
    body: IssuancePayRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:create"))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    service = IssuanceService(db, ctx, provider, ReferenceDataCache(get_redis_client()))
    data = await service.pay(body)
    await db.commit()
    return success_response(
        data,
        message="Payment processed",
        request_id=getattr(request.state, "request_id", None),
        job_id=(data.get("payment") or {}).get("job_id"),
    )
