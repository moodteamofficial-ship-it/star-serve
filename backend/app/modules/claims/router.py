"""Explicit claim domain actions. Status is never accepted from the client."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db, require_permissions
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.core.security.filenames import content_disposition_header
from app.core.security.request import client_ip
from app.modules.claims.models import Claim
from app.modules.claims.schemas import (
    ClaimAmendmentRequest,
    ClaimAmendmentReviewRequest,
    ClaimApproveRequest,
    ClaimAssignRequest,
    ClaimClientMessageRequest,
    ClaimCreateRequest,
    ClaimFollowupCompleteRequest,
    ClaimFollowupCreateRequest,
    ClaimInsurerDecisionRequest,
    ClaimNoteRequest,
    ClaimPaymentAuthorizeRequest,
    ClaimPaymentExecuteRequest,
    ClaimReasonRequest,
    ClaimSettlementRequest,
    ClaimStartVettingRequest,
    ClaimUpdateRequest,
    ClaimVersionRequest,
    ClaimVetRequest,
)
from app.modules.claims.service import ClaimService
from app.modules.system_config.deps import require_system_service

router = APIRouter(prefix="/claims", tags=["Claims"])


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _written(
    request: Request,
    db: AsyncSession,
    service: ClaimService,
    claim: Claim,
    message: str,
) -> dict:
    data = await service.present(claim)
    await db.commit()
    return success_response(data, message=message, request_id=_rid(request))


@router.get("/dashboard")
async def claims_dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
) -> dict:
    service = ClaimService(db, ctx)
    data = await service.dashboard()
    return success_response(data, request_id=_rid(request))


@router.get("")
async def list_claims(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
    status: Annotated[str | None, Query(max_length=48)] = None,
    assigned_to_me: Annotated[bool, Query()] = False,
    queue: Annotated[str | None, Query(max_length=32)] = None,
) -> dict:
    service = ClaimService(db, ctx)
    items, total = await service.list(
        page=page,
        limit=limit,
        query=q,
        status=status,
        assigned_to_me=assigned_to_me,
        queue=queue,
    )
    return success_response(
        {"items": items, "page": page, "limit": limit, "total": total},
        request_id=_rid(request),
    )


@router.post("")
async def create_claim(
    body: ClaimCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:create"))],
    _: Annotated[None, Depends(require_system_service("claims"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.create(body)
    return await _written(request, db, service, claim, "Claim created")


@router.get("/{claim_id}/assignees")
async def list_claim_assignees(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:assign"))],
) -> dict:
    service = ClaimService(db, ctx)
    items = await service.list_assignees(claim_id)
    return success_response({"items": items}, request_id=_rid(request))


@router.get("/{claim_id}")
async def get_claim(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
) -> dict:
    service = ClaimService(db, ctx)
    data = await service.get(claim_id)
    return success_response(data, request_id=_rid(request))


@router.post("/{claim_id}/view")
async def record_claim_view(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.record_view(
        claim_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return await _written(request, db, service, claim, "Claim viewed")


@router.get("/{claim_id}/pdf")
async def download_claim_pdf(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
    disposition: Annotated[Literal["inline", "attachment"], Query()] = "inline",
) -> Response:
    service = ClaimService(db, ctx)
    content, filename = await service.download_pdf(
        claim_id,
        disposition=disposition,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition_header(disposition, filename),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{claim_id}/update")
async def update_claim(
    claim_id: UUID,
    body: ClaimUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:update"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.update(claim_id, body)
    return await _written(request, db, service, claim, "Claim updated")


@router.post("/{claim_id}/submit")
async def submit_claim(
    claim_id: UUID,
    body: ClaimVersionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:update"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.submit(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Claim submitted")


@router.post("/{claim_id}/assign")
async def assign_claim(
    claim_id: UUID,
    body: ClaimAssignRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:assign"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.assign(claim_id, body)
    return await _written(request, db, service, claim, "Claim assigned")


@router.post("/{claim_id}/start-vetting")
async def start_vetting(
    claim_id: UUID,
    body: ClaimStartVettingRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:vet"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.start_vetting(claim_id, version=body.version, task=body.task)
    return await _written(request, db, service, claim, "Vetting started")


@router.post("/{claim_id}/vet")
async def vet_claim(
    claim_id: UUID,
    body: ClaimVetRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:vet"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.complete_vetting(claim_id, body)
    return await _written(request, db, service, claim, "Vetting recorded")


@router.post("/{claim_id}/request-information")
async def request_information(
    claim_id: UUID,
    body: ClaimReasonRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:request_information"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.request_information(claim_id, version=body.version, reason=body.reason)
    return await _written(request, db, service, claim, "Information requested")


@router.post("/{claim_id}/resume-vetting")
async def resume_vetting(
    claim_id: UUID,
    body: ClaimVersionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:vet"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.resume_vetting(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Vetting resumed")


@router.post("/{claim_id}/forward-to-definite")
async def forward_to_definite(
    claim_id: UUID,
    body: ClaimVersionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:forward"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.forward_to_definite(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Forwarded to Definite")


@router.post("/{claim_id}/record-insurer-decision")
async def record_insurer_decision(
    claim_id: UUID,
    body: ClaimInsurerDecisionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.record_insurer_decision(claim_id, body)
    return await _written(request, db, service, claim, "Insurer decision recorded")


@router.post("/{claim_id}/record-settlement")
async def record_settlement(
    claim_id: UUID,
    body: ClaimSettlementRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:read"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.record_settlement(claim_id, body)
    return await _written(request, db, service, claim, "Settlement recorded")


@router.post("/{claim_id}/approve")
async def approve_claim(
    claim_id: UUID,
    body: ClaimApproveRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:approve"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.approve(claim_id, version=body.version, reason=body.reason)
    return await _written(request, db, service, claim, "Approval recorded")


@router.post("/{claim_id}/reject")
async def reject_claim(
    claim_id: UUID,
    body: ClaimReasonRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:reject"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.reject(claim_id, version=body.version, reason=body.reason)
    return await _written(request, db, service, claim, "Claim rejected")


@router.post("/{claim_id}/withdraw")
async def withdraw_claim(
    claim_id: UUID,
    body: ClaimReasonRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:update"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.withdraw(claim_id, version=body.version, reason=body.reason)
    return await _written(request, db, service, claim, "Claim withdrawn")


@router.post("/{claim_id}/request-payment")
async def request_payment(
    claim_id: UUID,
    body: ClaimVersionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:payment:authorize"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.request_payment(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Payment requested")


@router.post("/{claim_id}/authorize-payment")
async def authorize_payment(
    claim_id: UUID,
    body: ClaimPaymentAuthorizeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:payment:authorize"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.authorize_payment(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Payment authorized")


@router.post("/{claim_id}/execute-payment")
async def execute_payment(
    claim_id: UUID,
    body: ClaimPaymentExecuteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:payment:execute"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.execute_payment(claim_id, version=body.version, idempotency_key=body.idempotency_key)
    return await _written(request, db, service, claim, "Payment submitted")


@router.post("/{claim_id}/retry-payment")
async def retry_payment(
    claim_id: UUID,
    body: ClaimPaymentExecuteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:payment:retry"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.retry_payment(claim_id, version=body.version, idempotency_key=body.idempotency_key)
    return await _written(request, db, service, claim, "Payment retry requested")


@router.post("/{claim_id}/close")
async def close_claim(
    claim_id: UUID,
    body: ClaimVersionRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:close"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.close(claim_id, version=body.version)
    return await _written(request, db, service, claim, "Claim closed")


@router.post("/{claim_id}/notes")
async def add_internal_note(
    claim_id: UUID,
    body: ClaimNoteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:note:create"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.add_note(claim_id, body)
    return await _written(request, db, service, claim, "Internal note added")


@router.post("/{claim_id}/client-messages")
async def send_client_message(
    claim_id: UUID,
    body: ClaimClientMessageRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:client:message"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.send_client_message(claim_id, subject=body.subject, message=body.message)
    return await _written(request, db, service, claim, "Client message recorded")


@router.post("/{claim_id}/followups")
async def create_followup(
    claim_id: UUID,
    body: ClaimFollowupCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:followup:create"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.create_followup(claim_id, body)
    return await _written(request, db, service, claim, "Follow-up created")


@router.post("/{claim_id}/followups/{followup_id}/complete")
async def complete_followup(
    claim_id: UUID,
    followup_id: UUID,
    body: ClaimFollowupCompleteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:followup:complete"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.complete_followup(claim_id, followup_id)
    return await _written(request, db, service, claim, "Follow-up completed")


@router.post("/{claim_id}/amendments")
async def request_amendment(
    claim_id: UUID,
    body: ClaimAmendmentRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:approve"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.request_amendment(claim_id, body)
    return await _written(request, db, service, claim, "Amendment requested")


@router.post("/{claim_id}/amendments/{amendment_id}/review")
async def review_amendment(
    claim_id: UUID,
    amendment_id: UUID,
    body: ClaimAmendmentReviewRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:approve"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.review_amendment(claim_id, amendment_id, body)
    return await _written(request, db, service, claim, "Amendment reviewed")


@router.post("/{claim_id}/documents")
async def upload_document(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:document:upload"))],
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "OTHER",
) -> dict:
    service = ClaimService(db, ctx)
    payload = await file.read()
    claim = await service.upload_document(
        claim_id,
        kind=kind[:32],
        filename=file.filename or "document",
        payload=payload,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return await _written(request, db, service, claim, "Document uploaded")


@router.get("/{claim_id}/documents/{document_id}")
async def download_document(
    claim_id: UUID,
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:document:download"))],
) -> Response:
    service = ClaimService(db, ctx)
    document, payload = await service.download_document(
        claim_id,
        document_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return Response(
        content=payload,
        media_type=document.content_type,
        headers={
            "Content-Disposition": content_disposition_header("attachment", document.original_filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{claim_id}/documents/{document_id}/delete")
async def delete_document(
    claim_id: UUID,
    document_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("claim:document:delete"))],
) -> dict:
    service = ClaimService(db, ctx)
    claim = await service.delete_document(claim_id, document_id)
    return await _written(request, db, service, claim, "Document removed")
