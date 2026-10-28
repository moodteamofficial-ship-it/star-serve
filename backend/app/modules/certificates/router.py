"""Certificate HTTP routes."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.core.security.request import client_ip as request_client_ip
from app.integrations.insurance.factory import get_insurance_provider
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.certificates.access_enums import CertificateAccessKind
from app.modules.certificates.service import (
    CertificateService,
    access_to_public,
    to_public,
)
from app.modules.system_config.deps import require_system_service
from app.modules.payments.schemas import CertificatePublic

router = APIRouter(prefix="/certificates", tags=["Certificates"])


def _provider() -> InsuranceProvider:
    return get_insurance_provider()


def _client_ip(request: Request) -> str | None:
    return request_client_ip(request)


@router.get("")
async def list_certificates(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("certificate:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    policy_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = CertificateService(db, ctx, provider)
    rows, total = await service.list(
        page=page, limit=limit, policy_id=policy_id, status=status
    )
    customer_names = await service.customer_names_for(rows)
    vehicle_regs = await service.vehicle_registrations_for(rows)
    return success_response(
        {
            "items": [
                CertificatePublic.model_validate(
                    to_public(
                        r,
                        customer_name=customer_names.get(r.customer_id),
                        vehicle_registration=vehicle_regs.get(r.policy_id),
                    )
                ).model_dump(mode="json")
                for r in rows
            ],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{certificate_id}/download")
async def download_certificate(
    certificate_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("certificate:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    disposition: Annotated[
        Literal["inline", "attachment"], Query()
    ] = "inline",
) -> Response:
    """Stream certificate PDF. ``inline`` = view/open; ``attachment`` = download."""
    service = CertificateService(db, ctx, provider)
    access_kind = (
        CertificateAccessKind.DOWNLOAD
        if disposition == "attachment"
        else CertificateAccessKind.VIEW
    )
    content, filename = await service.download_pdf(
        certificate_id,
        access_kind=access_kind,
        ip_address=_client_ip(request),
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


@router.get("/{certificate_id}/accesses")
async def list_certificate_accesses(
    certificate_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("certificate:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    service = CertificateService(db, ctx, provider)
    rows, total = await service.list_file_accesses(
        certificate_id, page=page, limit=limit
    )
    return success_response(
        {
            "items": [access_to_public(r) for r in rows],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{certificate_id}")
async def get_certificate(
    certificate_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("certificate:read"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
) -> dict:
    service = CertificateService(db, ctx, provider)
    row = await service.get(certificate_id)
    customer_names = await service.customer_names_for([row])
    vehicle_regs = await service.vehicle_registrations_for([row])
    return success_response(
        CertificatePublic.model_validate(
            to_public(
                row,
                customer_name=customer_names.get(row.customer_id),
                vehicle_registration=vehicle_regs.get(row.policy_id),
            )
        ).model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )


@router.post("/policies/{policy_id}/generate")
async def generate_certificate(
    policy_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("certificate:generate"))],
    provider: Annotated[InsuranceProvider, Depends(_provider)],
    _: Annotated[None, Depends(require_system_service("certificates"))],
) -> dict:
    service = CertificateService(db, ctx, provider)
    row = await service.generate_for_policy(policy_id)
    await db.commit()
    return success_response(
        CertificatePublic.model_validate(to_public(row)).model_dump(mode="json"),
        message="Certificate generated",
        request_id=getattr(request.state, "request_id", None),
        job_id=row.job_id,
    )
