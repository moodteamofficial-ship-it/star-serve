"""Payment HTTP routes + signed M-Pesa webhook."""

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies.auth import get_db, require_permissions
from app.core.exceptions import AuthenticationError
from app.core.responses import success_response
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.payments.schemas import (
    PaymentInitiateRequest,
    PaymentPublic,
    PaymentReceiptConfirmRequest,
)
from app.modules.payments.service import PaymentService, to_public
from app.modules.system_config.deps import require_system_service

router = APIRouter(prefix="/payments", tags=["Payments"])
webhook_router = APIRouter(prefix="/webhooks/payments", tags=["Payment Webhooks"])


def _provider() -> InsuranceProvider:
    return get_insurance_provider()


def _require_allowed_callback_source(request: Request, allowlist: str) -> None:
    """Reject provider callbacks from unexpected sources when an allowlist exists.

    Signed-URL possession is not a strong claim on its own: the URL travels through
    the provider, its logs, and ours. When the provider publishes fixed egress IPs,
    this is what stops a leaked callback URL from being replayed by anyone else.
    """
    from app.core.security.request import client_ip, ip_in_allowlist

    if not (allowlist or "").strip():
        return
    # client_ip uses the socket peer, or the rightmost trusted XFF hop.
    # The leftmost XFF value is caller-controlled and is never used here.
    ip = client_ip(request)
    if not ip_in_allowlist(ip, allowlist):
        raise AuthenticationError("Callback source is not allowed")


def _webhook_security_context() -> SecurityContext:
    """Synthetic actor for signed provider callbacks — RLS bypass, not platform admin."""
    return SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="webhook@starserve.local",
        role_id=uuid4(),
        role_code="webhook",
        is_platform_admin=False,
        tenant_status="ACTIVE",
        permissions=set(),
        branch_scope=BranchScope.ALL_TENANT,
    )


@router.get("")
async def list_payments(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = PaymentService(db, ctx, provider)
    rows, total = await service.list(page=page, limit=limit, query=q, status=status)
    attrs = await service.attribution_for_payments(rows)
    return success_response(
        {
            "items": [
                PaymentPublic.model_validate(
                    to_public(r, attribution=attrs.get(r.id))
                ).model_dump(mode="json")
                for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/{payment_id}")
async def get_payment(
    payment_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = PaymentService(db, ctx, provider)
    row = await service.get(payment_id)
    attrs = await service.attribution_for_payments([row])
    await db.commit()
    return success_response(
        PaymentPublic.model_validate(
            to_public(row, attribution=attrs.get(row.id))
        ).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/{payment_id}/confirm-receipt")
async def confirm_payment_receipt(
    payment_id: UUID,
    body: PaymentReceiptConfirmRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:reconcile"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    """Staff-only reconcile when a provider callback never arrives.

    Requires ``payment:reconcile`` (finance / agency admin). Guests cannot confirm
    receipts — that path is customer STK + signed webhook.
    """
    service = PaymentService(db, ctx, provider)
    row = await service.confirm_receipt(payment_id, receipt=body.receipt)
    await db.commit()
    return success_response(
        PaymentPublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Payment confirmed from M-Pesa receipt",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("")
async def initiate_payment(
    body: PaymentInitiateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("payment:create"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    _: Annotated[None, Depends(require_system_service("payments"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    service = PaymentService(db, ctx, provider)
    result = await service.initiate(body, idempotency_key=idempotency_key)
    await db.commit()
    if isinstance(result, dict):
        data = result
        job_id = data.get("job_id")
    else:
        data = PaymentPublic.model_validate(to_public(result)).model_dump(mode="json")
        job_id = result.job_id
    return success_response(
        data,
        message="Payment initiated",
        request_id=getattr(request.state, "request_id", None),
        job_id=job_id,
    )


@webhook_router.post("/mpesa")
async def mpesa_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    """Provider callback — signature verified; no cookie session required."""
    _require_allowed_callback_source(request, get_settings().mpesa_callback_allowed_ips)
    payload: dict[str, Any] = await request.json()
    headers = {k: v for k, v in request.headers.items()}
    # Synthetic context; service rebinds tenant after payment lookup
    ctx = _webhook_security_context()
    ctx.bind()
    service = PaymentService(db, ctx, provider)
    row = await service.apply_webhook(headers=headers, payload=payload, method="MPESA")
    await db.commit()
    return success_response(
        {"reference": row.reference, "status": row.status},
        message="Webhook processed",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@webhook_router.post("/birdview")
@webhook_router.post("/birdview/{reference}/{sig}")
@webhook_router.post("/birdview/{reference}/{amt}/{exp}/{sig}")
async def birdview_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    reference: str | None = None,
    sig: str | None = None,
    amt: str | None = None,
    exp: str | None = None,
) -> dict:
    """BirdView STK callback — HMAC from path/query + flexible body shape."""
    _require_allowed_callback_source(request, get_settings().birdview_callback_allowed_ips)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {"data": body}

    # Minted sig/ref travel on the callbackUrl path and query string.
    payload = {
        **body,
        **{k: v for k, v in request.query_params.items()},
    }
    if reference:
        payload.setdefault("ref", reference)
    if sig:
        payload.setdefault("sig", sig)
    if amt:
        payload.setdefault("amt", amt)
    if exp:
        payload.setdefault("exp", exp)
    headers = {k: v for k, v in request.headers.items()}
    ctx = _webhook_security_context()
    ctx.bind()
    service = PaymentService(db, ctx, provider)
    row = await service.apply_webhook(headers=headers, payload=payload, method="BIRDVIEW")
    await db.commit()
    # Acknowledge like Daraja — avoid provider retries on success path.
    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted",
        "reference": row.reference,
        "status": row.status,
    }
