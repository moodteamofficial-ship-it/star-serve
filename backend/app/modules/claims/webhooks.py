"""Signed Definite and payout callbacks — never accept an internal claim id as authority."""

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.database.rls import set_rls_context
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.responses import success_response
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext
from app.modules.claims.callbacks import payload_hash, verify_signed_callback
from app.modules.claims.service import ClaimService

webhook_router = APIRouter(prefix="/webhooks/claims", tags=["Claim Webhooks"])


def _webhook_context() -> SecurityContext:
    return SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="claims-webhook@starserve.local",
        role_id=uuid4(),
        role_code="webhook",
        is_platform_admin=False,
        tenant_status="ACTIVE",
        permissions=set(),
        branch_scope=BranchScope.ALL_TENANT,
    )


async def _session() -> AsyncSession:
    factory = get_session_factory()
    session = factory()
    await set_rls_context(session, tenant_id=None, rls_bypass=True)
    return session


@webhook_router.post("/definite")
async def definite_callback(request: Request) -> dict:
    raw = await request.body()
    body = verify_signed_callback(
        payload=raw,
        signature=request.headers.get("x-definite-signature"),
        timestamp=request.headers.get("x-definite-timestamp"),
        nonce=request.headers.get("x-definite-nonce"),
    )
    reference = str(body.get("external_reference") or "").strip()
    decision = str(body.get("decision") or "").strip()
    if not reference:
        raise AuthenticationError("Callback is missing the external reference")
    # Internal claim_id, if present, is ignored as an authority signal.
    amount_raw = body.get("approved_amount")
    amount = Decimal(str(amount_raw)) if amount_raw not in (None, "") else None
    session = await _session()
    ctx = _webhook_context()
    try:
        service = ClaimService(session, ctx)
        replay = await service.remember_webhook(
            provider="DEFINITE",
            nonce=request.headers.get("x-definite-nonce") or "",
            timestamp_header=request.headers.get("x-definite-timestamp"),
            payload_hash=payload_hash(raw),
            external_reference=reference,
            claim_id=None,
            result="RECEIVED",
        )
        if replay is not None:
            return success_response(
                {"replay": True, "result": replay.result},
                message="Callback already processed",
                request_id=getattr(request.state, "request_id", None),
            )
        claim = await service.apply_definite_decision(
            external_reference=reference,
            decision=decision,
            approved_amount=amount,
            payload_reference=payload_hash(raw),
        )
        await session.commit()
        return success_response(
            {"claim_id": str(claim.id), "status": claim.status},
            message="Definite decision applied",
            request_id=getattr(request.state, "request_id", None),
        )
    except ConflictError:
        await session.rollback()
        raise
    finally:
        await session.close()


@webhook_router.post("/payments")
async def payment_callback(request: Request) -> dict:
    raw = await request.body()
    body = verify_signed_callback(
        payload=raw,
        signature=request.headers.get("x-payout-signature"),
        timestamp=request.headers.get("x-payout-timestamp"),
        nonce=request.headers.get("x-payout-nonce"),
    )
    reference = str(body.get("provider_reference") or "").strip()
    if not reference:
        raise AuthenticationError("Callback is missing the provider reference")
    success = bool(body.get("success"))
    session = await _session()
    ctx = _webhook_context()
    try:
        service = ClaimService(session, ctx)
        replay = await service.remember_webhook(
            provider="CLAIM_PAYOUT",
            nonce=request.headers.get("x-payout-nonce") or "",
            timestamp_header=request.headers.get("x-payout-timestamp"),
            payload_hash=payload_hash(raw),
            external_reference=reference,
            claim_id=None,
            result="RECEIVED",
        )
        if replay is not None:
            return success_response(
                {"replay": True, "result": replay.result},
                message="Callback already processed",
                request_id=getattr(request.state, "request_id", None),
            )
        claim = await service.apply_payment_outcome(
            provider_reference=reference,
            success=success,
            failure_reason=str(body.get("failure_reason") or "") or None,
            payload_reference=payload_hash(raw),
        )
        await session.commit()
        return success_response(
            {"claim_id": str(claim.id), "status": claim.status},
            message="Payment outcome applied",
            request_id=getattr(request.state, "request_id", None),
        )
    finally:
        await session.close()
