"""FOLLOW_UP_CLAIM — reuses GuestClaimService.lookup with identity verification."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StarServeError, ValidationAppError
from app.core.validation.identity import normalize_id_number, normalize_phone
from app.integrations.notifications.sms.provider import to_local_msisdn
from app.modules.claims.guest_schemas import GuestClaimLookupRequest
from app.modules.claims.guest_service import GuestClaimService
from app.modules.ussd.channel import prepare_ussd_request, ussd_guest_context
from app.modules.ussd.enums import (
    UssdEventType,
    UssdOutcomeCategory,
    UssdResponseType,
    UssdWorkflowAction,
)
from app.modules.ussd.models import UssdSession
from app.modules.ussd.workflows.base import WorkflowResult


def _public_status(data: dict) -> str:
    status = str(data.get("status") or data.get("status_label") or "UPDATED").replace("_", " ")
    number = str(data.get("claim_number") or data.get("number") or "")
    next_action = str(data.get("next_action") or data.get("extra_notice") or "").strip()
    lines = [f"Claim {number}", f"Status: {status}"]
    if next_action:
        lines.append(next_action[:80])
    lines.append("Thank you.")
    return "\n".join(lines)


class FollowUpClaimWorkflow:
    action = UssdWorkflowAction.FOLLOW_UP_CLAIM.value

    async def start(self, session: AsyncSession, ussd: UssdSession) -> WorkflowResult:
        return WorkflowResult(
            message="Follow up a claim\nEnter claim number\n0 Back  00 Main menu",
            step="claim_number",
            event_type=UssdEventType.WORKFLOW_ENTERED.value,
            outcome=UssdOutcomeCategory.IN_PROGRESS.value,
        )

    async def handle(
        self, session: AsyncSession, ussd: UssdSession, text: str
    ) -> WorkflowResult:
        step = ussd.workflow_step or "claim_number"
        answers = dict(ussd.answers or {})
        value = (text or "").strip()

        if step == "claim_number":
            cleaned = value.upper().replace(" ", "")
            if len(cleaned) < 6 or len(cleaned) > 32:
                return WorkflowResult(
                    message="Invalid claim reference. Enter at least 6 characters.",
                    step=step,
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                    error_category="INVALID_CLAIM_REF",
                )
            answers["claim_number"] = cleaned
            return WorkflowResult(
                message="Enter national ID or passport\n0 Back 00 Main menu",
                step="id_number",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "id_number":
            try:
                answers["id_number"] = normalize_id_number(value)
            except ValidationAppError:
                return WorkflowResult(
                    message="Invalid ID. Use 5-32 letters or digits.",
                    step=step,
                    event_type=UssdEventType.VALIDATION_FAILED.value,
                    outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
                    error_category="INVALID_ID",
                )
            phone_raw = str(answers.get("msisdn") or "")
            local = to_local_msisdn(phone_raw) or phone_raw
            try:
                phone = normalize_phone(local)
            except ValidationAppError:
                return WorkflowResult(
                    message="Could not read your phone from this dial. Contact the agency.",
                    response_type=UssdResponseType.END.value,
                    clear_workflow=True,
                    event_type=UssdEventType.BUSINESS_REJECTED.value,
                    outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                    error_category="INVALID_PHONE",
                )
            guest = ussd_guest_context(
                tenant_id=UUID(str(ussd.tenant_id)),
                guest_session_id=ussd.guest_session_id or ussd.id,
            )
            request = prepare_ussd_request(
                msisdn=phone_raw,
                correlation_id=ussd.correlation_id,
                guest=guest,
                is_test=ussd.is_test,
            )
            service = GuestClaimService(session, guest, request)
            body = GuestClaimLookupRequest(
                claim_number=str(answers["claim_number"]),
                id_number=str(answers["id_number"]),
                phone=phone,
            )
            try:
                data = await service.lookup(body)
            except ValidationAppError as exc:
                return WorkflowResult(
                    message=str(getattr(exc, "message", None) or exc)[:160],
                    response_type=UssdResponseType.END.value,
                    clear_workflow=True,
                    event_type=UssdEventType.BUSINESS_REJECTED.value,
                    outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                    error_category="CLAIM_NOT_FOUND",
                )
            except StarServeError as exc:
                return WorkflowResult(
                    message=str(getattr(exc, "message", None) or exc)[:160],
                    response_type=UssdResponseType.END.value,
                    clear_workflow=True,
                    event_type=UssdEventType.TECHNICAL_ERROR.value,
                    outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
                )
            answers["claim_id"] = str(data.get("id") or "")
            return WorkflowResult(
                message=_public_status(data),
                response_type=UssdResponseType.END.value,
                answers_patch=answers,
                clear_workflow=True,
                event_type=UssdEventType.WORKFLOW_SUCCEEDED.value,
                outcome=UssdOutcomeCategory.SUCCESS.value,
            )

        return WorkflowResult(
            message="Session error. Dial again.",
            response_type=UssdResponseType.END.value,
            clear_workflow=True,
            event_type=UssdEventType.TECHNICAL_ERROR.value,
            outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
        )
