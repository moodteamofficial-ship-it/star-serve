"""Server-computed UI capabilities. Hiding a button is not a security control."""

from __future__ import annotations

from app.core.security.context import SecurityContext
from app.modules.claims.authorization import (
    PERM_APPROVE,
    PERM_ASSIGN,
    PERM_CLIENT_MESSAGE,
    PERM_CLOSE,
    PERM_DOC_DELETE,
    PERM_DOC_DOWNLOAD,
    PERM_DOC_UPLOAD,
    PERM_FOLLOWUP_COMPLETE,
    PERM_FOLLOWUP_CREATE,
    PERM_FORWARD,
    PERM_NOTE_CREATE,
    PERM_NOTE_READ,
    PERM_PAY_AUTH,
    PERM_PAY_EXEC,
    PERM_PAY_READ,
    PERM_PAY_RETRY,
    PERM_RECOMMEND,
    PERM_REJECT,
    PERM_REQUEST_INFO,
    PERM_UPDATE,
    PERM_VET,
    PERM_VIEW_SENSITIVE,
    can_supervise,
    editable_fields,
    is_assignee,
    is_creator,
)
from app.modules.claims.enums import ClaimStatus, TERMINAL_STATUSES
from app.modules.claims.models import Claim
from app.modules.claims.schemas import ClaimCapabilities


def _can(ctx: SecurityContext, permission: str, claim: Claim, *, assigned: bool) -> bool:
    if not ctx.allows(permission):
        return False
    if assigned:
        return True
    if can_supervise(ctx):
        return True
    if permission == PERM_UPDATE and is_creator(ctx, claim) and claim.status == ClaimStatus.CLAIM_DRAFT.value:
        return True
    return False


def compute_capabilities(
    ctx: SecurityContext,
    claim: Claim,
    *,
    already_approved: bool = False,
) -> ClaimCapabilities:
    assigned = is_assignee(ctx, claim)
    terminal = claim.status in TERMINAL_STATUSES
    status = claim.status

    can_edit = (
        not terminal
        and bool(editable_fields(claim))
        and _can(ctx, PERM_UPDATE, claim, assigned=assigned)
    )
    caps = ClaimCapabilities(
        can_view=True,
        can_edit=can_edit,
        can_assign=ctx.allows(PERM_ASSIGN) and not terminal,
        can_vet=_can(ctx, PERM_VET, claim, assigned=assigned)
        and status in {ClaimStatus.VETTING.value, ClaimStatus.CLAIM_SUBMITTED.value},
        can_request_information=_can(ctx, PERM_REQUEST_INFO, claim, assigned=assigned)
        and status == ClaimStatus.VETTING.value,
        can_recommend_approval=_can(ctx, PERM_RECOMMEND, claim, assigned=assigned)
        and status == ClaimStatus.VETTING_PASSED.value,
        can_approve=_can(ctx, PERM_APPROVE, claim, assigned=assigned)
        and status == ClaimStatus.VETTING_PASSED.value
        and not already_approved,
        already_approved=already_approved
        and status == ClaimStatus.VETTING_PASSED.value,
        can_reject=_can(ctx, PERM_REJECT, claim, assigned=assigned)
        and status
        in {
            ClaimStatus.VETTING.value,
            ClaimStatus.VETTING_PASSED.value,
            ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
        },
        can_forward=_can(ctx, PERM_FORWARD, claim, assigned=assigned)
        and status == ClaimStatus.VETTING_PASSED.value,
        can_record_insurer_decision=(ctx.allows(PERM_FORWARD) or ctx.allows(PERM_APPROVE))
        and status
        in {
            ClaimStatus.SENT_TO_DEFINITE.value,
            ClaimStatus.DEFINITE_REVIEW.value,
        },
        can_record_settlement=(
            ctx.allows(PERM_FORWARD) or ctx.allows(PERM_APPROVE) or ctx.allows(PERM_PAY_AUTH)
        )
        and status
        in {
            ClaimStatus.DEFINITE_APPROVED.value,
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.PAYMENT_AUTHORIZED.value,
            ClaimStatus.PAYMENT_PROCESSING.value,
            ClaimStatus.PAYMENT_FAILED.value,
            ClaimStatus.PAYMENT_REVIEW.value,
        },
        can_view_sensitive=ctx.allows(PERM_VIEW_SENSITIVE),
        can_upload_document=_can(ctx, PERM_DOC_UPLOAD, claim, assigned=assigned) and not terminal,
        can_delete_document=_can(ctx, PERM_DOC_DELETE, claim, assigned=assigned) and not terminal,
        can_download_document=ctx.allows(PERM_DOC_DOWNLOAD),
        can_view_notes=ctx.allows(PERM_NOTE_READ),
        can_add_note=_can(ctx, PERM_NOTE_CREATE, claim, assigned=assigned),
        can_send_client_message=_can(ctx, PERM_CLIENT_MESSAGE, claim, assigned=assigned),
        can_create_followup=_can(ctx, PERM_FOLLOWUP_CREATE, claim, assigned=assigned),
        can_complete_followup=_can(ctx, PERM_FOLLOWUP_COMPLETE, claim, assigned=assigned),
        can_authorize_payment=ctx.allows(PERM_PAY_AUTH)
        and status
        in {
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.PAYMENT_REVIEW.value,
        },
        can_execute_payment=ctx.allows(PERM_PAY_EXEC)
        and status == ClaimStatus.PAYMENT_AUTHORIZED.value,
        can_view_payment=ctx.allows(PERM_PAY_READ),
        can_retry_payment=ctx.allows(PERM_PAY_RETRY)
        and status in {ClaimStatus.PAYMENT_FAILED.value, ClaimStatus.PAYMENT_REVIEW.value},
        can_close=_can(ctx, PERM_CLOSE, claim, assigned=assigned)
        and status == ClaimStatus.CLIENT_NOTIFIED.value,
        can_amend=ctx.allows(PERM_APPROVE)
        and status
        in {
            ClaimStatus.DEFINITE_APPROVED.value,
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.VETTING_PASSED.value,
        },
    )
    sections = ["header", "policy", "claimant", "accident", "vehicle", "driver", "documents", "timeline"]
    if caps.can_vet or status not in {ClaimStatus.CLAIM_DRAFT.value}:
        sections.append("vetting")
    if status not in {ClaimStatus.CLAIM_DRAFT.value, ClaimStatus.CLAIM_SUBMITTED.value, ClaimStatus.VETTING.value}:
        sections.append("definite")
    if caps.can_approve or status in {
        ClaimStatus.VETTING_PASSED.value,
        ClaimStatus.DEFINITE_APPROVED.value,
        ClaimStatus.PAYMENT_PENDING.value,
        ClaimStatus.PAYMENT_AUTHORIZATION.value,
        ClaimStatus.PAYMENT_AUTHORIZED.value,
        ClaimStatus.PAYMENT_PROCESSING.value,
        ClaimStatus.PAYMENT_COMPLETED.value,
        ClaimStatus.CLOSED.value,
    }:
        sections.append("approvals")
    if caps.can_view_payment:
        sections.append("payment")
    sections.extend(["followups", "client_communications"])
    if caps.can_view_notes:
        sections.append("internal_notes")
    if caps.can_view_sensitive:
        sections.extend(["injuries", "damage"])
    else:
        sections.extend(["injuries", "damage"])
    caps.visible_sections = sections
    return caps
