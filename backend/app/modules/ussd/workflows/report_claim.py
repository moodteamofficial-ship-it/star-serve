"""REPORT_CLAIM — same fields and validators as WelcomeClaimModals / GuestClaimService."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, StarServeError, ValidationAppError
from app.core.validation.identity import (
    normalize_id_number,
    normalize_phone,
    normalize_vehicle_registration,
)
from app.integrations.notifications.sms.provider import to_local_msisdn
from app.modules.claims.enums import ClaimChannel
from app.modules.claims.guest_schemas import GuestClaimCreateRequest
from app.modules.claims.guest_service import GuestClaimService, policy_lookup_key
from app.modules.claims.models import Claim
from app.modules.ussd.channel import prepare_ussd_request, ussd_guest_context
from app.modules.ussd.enums import (
    UssdEventType,
    UssdOutcomeCategory,
    UssdResponseType,
    UssdWorkflowAction,
)
from app.modules.ussd.models import UssdSession
from app.modules.ussd.workflows.base import WorkflowResult

_NAV = "0 Back 00 Main menu"


def _nav(msg: str) -> str:
    return f"{msg}\n{_NAV}"


def _err_text(exc: Exception) -> str:
    return str(getattr(exc, "message", None) or exc)[:160]


def _validation_fail(message: str, step: str, category: str) -> WorkflowResult:
    return WorkflowResult(
        message=message,
        step=step,
        event_type=UssdEventType.VALIDATION_FAILED.value,
        outcome=UssdOutcomeCategory.VALIDATION_FAILURE.value,
        error_category=category,
    )


def _parse_ddmmyyyy(raw: str) -> date:
    text = raw.strip().replace("/", "").replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValidationAppError("Use date as DDMMYYYY")
    day, month, year = int(text[:2]), int(text[2:4]), int(text[4:])
    return date(year, month, day)


class ReportClaimWorkflow:
    action = UssdWorkflowAction.REPORT_CLAIM.value

    async def start(self, session: AsyncSession, ussd: UssdSession) -> WorkflowResult:
        return WorkflowResult(
            message=_nav("Report a claim\nEnter policy or certificate number"),
            step="policy_number",
            event_type=UssdEventType.WORKFLOW_ENTERED.value,
            outcome=UssdOutcomeCategory.IN_PROGRESS.value,
        )

    async def handle(
        self, session: AsyncSession, ussd: UssdSession, text: str
    ) -> WorkflowResult:
        step = ussd.workflow_step or "policy_number"
        answers = dict(ussd.answers or {})
        value = (text or "").strip()

        if step == "policy_number":
            try:
                answers["policy_number"] = policy_lookup_key(value)
            except ValidationAppError:
                return _validation_fail(
                    "Invalid policy or certificate number. Try again.",
                    step,
                    "INVALID_POLICY",
                )
            return WorkflowResult(
                message=_nav("Enter vehicle registration"),
                step="vehicle_registration",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "vehicle_registration":
            try:
                answers["vehicle_registration"] = normalize_vehicle_registration(value)
            except ValidationAppError:
                return _validation_fail(
                    "Invalid registration. Use letters and digits, e.g. KDA123A.",
                    step,
                    "INVALID_VEHICLE",
                )
            return WorkflowResult(
                message=_nav("Enter national ID or passport"),
                step="id_number",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "id_number":
            try:
                answers["id_number"] = normalize_id_number(value)
            except ValidationAppError:
                return _validation_fail(
                    "Invalid ID. Use 5-32 letters or digits.",
                    step,
                    "INVALID_ID",
                )
            return WorkflowResult(
                message=_nav("Enter phone on the policy"),
                step="phone",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "phone":
            try:
                answers["phone"] = normalize_phone(value)
            except ValidationAppError:
                return _validation_fail(
                    "Invalid phone. Use 9-15 digits, e.g. 0712345678.",
                    step,
                    "INVALID_PHONE",
                )
            return WorkflowResult(
                message=_nav("Enter incident date as DDMMYYYY"),
                step="incident_date",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "incident_date":
            try:
                incident = _parse_ddmmyyyy(value)
            except (ValidationAppError, ValueError):
                return _validation_fail(
                    "Use date as DDMMYYYY. Try again.",
                    step,
                    "INVALID_DATE",
                )
            if incident > date.today():
                return _validation_fail(
                    "Incident date cannot be in the future. Try again.",
                    step,
                    "FUTURE_DATE",
                )
            answers["incident_date"] = incident.isoformat()
            return WorkflowResult(
                message=_nav("Enter incident location"),
                step="incident_location",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "incident_location":
            location = " ".join(value.split())
            if len(location) < 3:
                return _validation_fail(
                    "Location too short. Enter at least 3 characters.",
                    step,
                    "INVALID_LOCATION",
                )
            if len(location) > 255:
                return _validation_fail(
                    "Location too long. Keep under 255 characters.",
                    step,
                    "INVALID_LOCATION",
                )
            answers["incident_location"] = location
            return WorkflowResult(
                message=_nav("Briefly describe what happened"),
                step="incident_description",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "incident_description":
            description = " ".join(value.split())
            if len(description) < 10:
                return _validation_fail(
                    "Description too short. Enter at least 10 characters.",
                    step,
                    "INVALID_DESCRIPTION",
                )
            answers["incident_description"] = description[:4000]
            summary = (
                "Confirm claim\n"
                f"Policy: {answers['policy_number']}\n"
                f"Reg: {answers['vehicle_registration']}\n"
                f"Date: {answers['incident_date']}\n"
                f"1. Submit\n{_NAV}"
            )
            return WorkflowResult(
                message=summary,
                step="confirm",
                answers_patch=answers,
                event_type=UssdEventType.STEP_COMPLETED.value,
            )

        if step == "confirm":
            if value != "1":
                return _validation_fail(
                    "Select 1 to submit, or 0 to go back.",
                    step,
                    "INVALID_CONFIRM",
                )
            return await self._submit(session, ussd, answers)

        return WorkflowResult(
            message="Session error. Dial again.",
            response_type=UssdResponseType.END.value,
            clear_workflow=True,
            event_type=UssdEventType.TECHNICAL_ERROR.value,
            outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
        )

    async def _submit(
        self, session: AsyncSession, ussd: UssdSession, answers: dict[str, Any]
    ) -> WorkflowResult:
        # Idempotency: if this session already filed a claim, return the same number.
        existing_ref = (answers.get("claim_number") or "").strip()
        if existing_ref:
            return WorkflowResult(
                message=(
                    f"Claim {existing_ref} already submitted. "
                    "Use Follow Up a Claim for status."
                ),
                response_type=UssdResponseType.END.value,
                answers_patch=answers,
                clear_workflow=True,
                event_type=UssdEventType.WORKFLOW_SUCCEEDED.value,
                outcome=UssdOutcomeCategory.SUCCESS.value,
            )

        phone = str(answers.get("phone") or "").strip()
        if not phone:
            # Fallback to dialed MSISDN only if phone step was skipped somehow.
            phone = to_local_msisdn(str(answers.get("msisdn") or "")) or str(
                answers.get("msisdn") or ""
            )
        try:
            phone = normalize_phone(phone)
        except ValidationAppError as exc:
            return WorkflowResult(
                message=_err_text(exc),
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
            msisdn=str(answers.get("msisdn") or phone),
            correlation_id=ussd.correlation_id,
            guest=guest,
            is_test=ussd.is_test,
        )
        service = GuestClaimService(session, guest, request)
        body = GuestClaimCreateRequest(
            policy_number=str(answers["policy_number"]),
            vehicle_registration=str(answers["vehicle_registration"]),
            id_number=str(answers["id_number"]),
            phone=phone,
            incident_date=date.fromisoformat(str(answers["incident_date"])),
            incident_location=str(answers["incident_location"]),
            incident_description=str(answers["incident_description"]),
            claimed_amount=Decimal("0"),
        )
        try:
            data = await service.file(body)
        except ConflictError as exc:
            return WorkflowResult(
                message=_err_text(exc),
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                error_category="CLAIM_CONFLICT",
            )
        except ValidationAppError as exc:
            return WorkflowResult(
                message=_err_text(exc),
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.BUSINESS_REJECTED.value,
                outcome=UssdOutcomeCategory.BUSINESS_FAILURE.value,
                error_category="CLAIM_VALIDATION",
            )
        except StarServeError as exc:
            return WorkflowResult(
                message=_err_text(exc),
                response_type=UssdResponseType.END.value,
                clear_workflow=True,
                event_type=UssdEventType.TECHNICAL_ERROR.value,
                outcome=UssdOutcomeCategory.TECHNICAL_FAILURE.value,
                error_category="CLAIM_ERROR",
            )

        claim_number = str(data.get("claim_number") or data.get("number") or "")
        claim_id = data.get("id")
        if claim_id:
            claim = await session.get(Claim, UUID(str(claim_id)))
            if claim is not None:
                claim.channel = ClaimChannel.USSD.value
        answers["claim_number"] = claim_number
        answers["claim_id"] = str(claim_id or "")
        return WorkflowResult(
            message=(
                f"Claim submitted. Reference {claim_number}. "
                "Add photos on the website if needed. Thank you."
            ),
            response_type=UssdResponseType.END.value,
            answers_patch=answers,
            clear_workflow=True,
            event_type=UssdEventType.WORKFLOW_SUCCEEDED.value,
            outcome=UssdOutcomeCategory.SUCCESS.value,
        )
