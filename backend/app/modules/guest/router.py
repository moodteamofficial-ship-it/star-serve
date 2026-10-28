"""Guest quote HTTP surface — isolated from staff insurance routes."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.core.responses import success_response
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.core.security.request import client_ip as request_client_ip
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.certificates.access_enums import CertificateAccessKind
from app.modules.customers.schemas import CustomerPublic
from app.modules.customers.service import CustomerService
from app.modules.guest.deps import require_guest
from app.modules.guest.service import GuestService
from app.core.exceptions import ResourceNotFoundError, ValidationAppError
from app.modules.insurance.guest_session import (
    assert_guest_owns_customer,
    enforce_guest_agent_lookup_limit,
    enforce_guest_catalog_limit,
    enforce_guest_csrf_bootstrap_limit,
    enforce_guest_payment_poll_limit,
    enforce_guest_premium_limit,
    enforce_guest_tenant_list_limit,
    ensure_csrf_cookie,
    list_guest_tenants,
    mint_guest_session,
    require_trusted_origin,
)
from app.modules.insurance.issuance_schemas import (
    IssuanceClientRequest,
    IssuancePayCancelRequest,
    IssuancePayRequest,
    IssuanceSubmitRequest,
)
from app.modules.insurance.schemas import GuestSessionRequest, PremiumCalculateRequest, PremiumPublic
from app.modules.payments.schemas import PaymentPublic
from app.modules.payments.service import to_public

router = APIRouter(prefix="/insurance/guest", tags=["Guest Insurance"])


def get_provider() -> InsuranceProvider:
    return get_insurance_provider()


def _guest_service(
    db: AsyncSession,
    guest: GuestContext,
    provider: InsuranceProvider,
    request: Request,
) -> GuestService:
    return GuestService(db, guest, provider, request)


@router.get("/csrf")
async def guest_csrf_bootstrap(request: Request, response: Response) -> dict:
    """Issue the readable CSRF cookie without consuming the agency-list budget."""
    require_trusted_origin(request)
    await enforce_guest_csrf_bootstrap_limit(request)
    ensure_csrf_cookie(request, response)
    return success_response(
        {"ok": True},
        message="Guest CSRF ready",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/tenants")
async def guest_tenants(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Active agencies available for the welcome-screen guest quote picker."""
    await enforce_guest_tenant_list_limit(request)
    ensure_csrf_cookie(request, response)
    items = await list_guest_tenants(db)
    return success_response(
        {"items": items},
        message="Guest agencies loaded",
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/session")
async def create_guest_session(
    body: GuestSessionRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Mint a short-lived guest capability for the welcome quote screen only."""
    preferred: UUID | None = None
    if body.tenant_id:
        try:
            preferred = UUID(body.tenant_id.strip())
        except ValueError as exc:
            from app.core.exceptions import ValidationAppError

            raise ValidationAppError("tenant_id must be a valid UUID") from exc
    data = await mint_guest_session(
        request, db, response=response, tenant_id=preferred
    )
    await db.commit()
    return success_response(
        data,
        message="Guest quote session ready",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/agents/{agent_code}")
async def guest_resolve_agent(
    agent_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.VIEW_QUOTE))],
) -> dict:
    """Validate a scanned agent code for the welcome quote flow.

    Returns only public attribution fields for an APPROVED tenant agent.
    Invalid, pending, or suspended codes look the same (not found).

    Platform-tenant agents are re-homed onto the guest agency so QR scans
    match the welcome-session tenant (staff often create agents while on
    the platform tenant).
    """
    from sqlalchemy import select

    from app.core.database.rls import set_rls_bypass
    from app.core.security.branch_scope import first_active_tenant_branch_id
    from app.modules.intermediaries.models import Intermediary
    from app.modules.tenants.models import Tenant

    await enforce_guest_agent_lookup_limit(request)
    code = (agent_code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise ValidationAppError("Agent code must be 6 digits")

    # Guests are RLS-bound to the agency tenant; platform-created agents would
    # otherwise be invisible. Bypass briefly for this exact-code lookup only.
    await set_rls_bypass(db, True)
    try:
        row = await db.scalar(
            select(Intermediary).where(
                Intermediary.agent_code == code,
                Intermediary.deleted_at.is_(None),
            )
        )
        if row is None or str(row.status).upper() != "APPROVED":
            raise ResourceNotFoundError("That agent code is not valid")

        if row.tenant_id != guest.tenant_id:
            owner = await db.get(Tenant, row.tenant_id)
            if owner is not None and bool(owner.is_platform):
                row.tenant_id = guest.tenant_id
                branch_id = await first_active_tenant_branch_id(db, guest.tenant_id)
                if branch_id is not None:
                    row.branch_id = branch_id
                await db.flush()
                await db.commit()
            else:
                raise ResourceNotFoundError("That agent code is not valid")
    finally:
        await set_rls_bypass(db, False)

    return success_response(
        {
            "id": str(row.id),
            "name": row.name,
            "agent_code": row.agent_code,
        },
        message="Agent ready",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/referrals/{referral_code}")
async def guest_resolve_referral(
    referral_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.VIEW_QUOTE))],
) -> dict:
    """Validate a scanned customer referral code. Only the referrer's first name is shown."""
    from app.modules.referrals.service import ReferralService, normalize_referral_code

    await enforce_guest_agent_lookup_limit(request)
    if normalize_referral_code(referral_code) is None:
        raise ValidationAppError("That referral code is not valid")
    row = await ReferralService(db).resolve(referral_code)
    if row is None:
        raise ResourceNotFoundError("That referral code is not valid")
    first_name = ((row.holder_name or "").split() or [""])[0] or None
    return success_response(
        {"referral_code": row.code, "referrer_first_name": first_name},
        message="Referral code ready",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/catalog")
async def guest_catalog(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.VIEW_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    await enforce_guest_catalog_limit(request)
    data = await _guest_service(db, guest, provider, request).get_catalog()
    return success_response(
        data,
        message="Insurance catalog loaded",
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/premium")
async def guest_calculate_premium(
    body: PremiumCalculateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    await enforce_guest_premium_limit(request)
    data = await _guest_service(db, guest, provider, request).calculate_premium(body)
    await db.commit()
    return success_response(
        {
            "job_id": data["job_id"],
            "premium": PremiumPublic.model_validate(data["premium"]).model_dump(),
        },
        message="Premium calculated from insurance provider",
        request_id=getattr(request.state, "request_id", None),
    )


class GuestClientLookupRequest(BaseModel):
    id_number: str = Field(min_length=5, max_length=32)


@router.post("/client/lookup")
async def guest_client_lookup(
    body: GuestClientLookupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    """Returning-client hint for the guest quote — masked name only."""
    data = await _guest_service(db, guest, provider, request).lookup_returning_client(
        body.id_number
    )
    return success_response(
        data,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/client/returning")
async def guest_returning_client(
    body: GuestClientLookupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    """Continue a guest quote with a returning client's stored details (masked)."""
    data = await _guest_service(db, guest, provider, request).ensure_returning_client(
        body.id_number
    )
    await db.commit()
    return success_response(
        data,
        message="Client ready for issuance",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


class GuestIssuanceSubmitRequest(IssuanceSubmitRequest):
    # Vehicle identifiers come from the returning client's last proposal.
    use_last_vehicle: bool = False


@router.post("/client")
async def guest_issuance_client(
    body: IssuanceClientRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    data = await _guest_service(db, guest, provider, request).ensure_client(body)
    await db.commit()
    return success_response(
        data,
        message="Client ready for issuance",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/submit")
async def guest_issuance_submit(
    body: GuestIssuanceSubmitRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    data = await _guest_service(db, guest, provider, request).submit(
        IssuanceSubmitRequest(**body.model_dump(exclude={"use_last_vehicle"})),
        use_last_vehicle=body.use_last_vehicle,
    )
    await db.commit()
    return success_response(
        data,
        message="Proposal submitted and policy awaiting payment",
        request_id=getattr(request.state, "request_id", None),
        job_id=data.get("job_id"),
    )


@router.post("/pay")
async def guest_issuance_pay(
    body: IssuancePayRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext, Depends(require_guest(GuestCapability.INITIATE_PAYMENT))
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    data = await _guest_service(db, guest, provider, request).pay(body)
    await db.commit()
    return success_response(
        data,
        message="Payment processed",
        request_id=getattr(request.state, "request_id", None),
        job_id=(data.get("payment") or {}).get("job_id"),
    )


@router.post("/pay/cancel")
async def guest_issuance_pay_cancel(
    body: IssuancePayCancelRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext, Depends(require_guest(GuestCapability.INITIATE_PAYMENT))
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    try:
        policy_id = UUID(body.policy_id)
    except ValueError as exc:
        raise ValidationAppError("policy_id must be a valid UUID") from exc
    data = await _guest_service(db, guest, provider, request).cancel_payment(policy_id)
    await db.commit()
    return success_response(
        data,
        message="Payment cancelled" if data["cancelled"] else "Nothing to cancel",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/payments/{payment_id}")
async def guest_get_payment(
    payment_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.VIEW_PAYMENT))],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
) -> dict:
    await enforce_guest_payment_poll_limit(request)
    row = await _guest_service(db, guest, provider, request).get_payment(payment_id)
    await db.commit()
    return success_response(
        PaymentPublic.model_validate(to_public(row)).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/customers/{customer_id}/documents")
async def guest_upload_customer_document(
    customer_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.CREATE_QUOTE))],
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Guest KYC upload after certificate issuance (logbook + ID)."""
    assert_guest_owns_customer(request, customer_id)
    payload = await file.read()
    service = CustomerService(db, guest.as_execution_context())
    data = await service.upload_kyc_document(
        customer_id,
        kind=(kind or "").strip().lower(),
        payload=payload,
        filename=file.filename or "document",
    )
    await db.commit()
    return success_response(
        {
            "kind": data["kind"],
            "url": data["url"],
            "customer": CustomerPublic.model_validate(data["customer"]).model_dump(
                mode="json"
            ),
        },
        message="Document uploaded",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/certificates/{certificate_id}/download")
async def guest_download_certificate(
    certificate_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext, Depends(require_guest(GuestCapability.DOWNLOAD_CERTIFICATE))
    ],
    provider: Annotated[InsuranceProvider, Depends(get_provider)],
    disposition: Annotated[Literal["inline", "attachment"], Query()] = "inline",
) -> Response:
    access_kind = (
        CertificateAccessKind.DOWNLOAD
        if disposition == "attachment"
        else CertificateAccessKind.VIEW
    )
    content, filename = await _guest_service(
        db, guest, provider, request
    ).download_certificate(
        certificate_id,
        access_kind=access_kind,
        ip_address=request_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    from app.core.security.filenames import content_disposition_header

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition_header(disposition, filename),
            "Cache-Control": "private, max-age=60",
            "X-Certificate-Access": access_kind.value,
        },
    )
