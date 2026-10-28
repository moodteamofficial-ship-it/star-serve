"""Claims application service — every mutation is transactional and audited."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import UserStatus
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationAppError,
)
from app.core.security.context import SecurityContext
from app.core.storage import get_blob_store
from app.modules.claims.authorization import (
    PERM_APPROVE,
    PERM_ASSIGN,
    PERM_CLIENT_MESSAGE,
    PERM_CLOSE,
    PERM_CREATE,
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
    PERM_REJECT,
    PERM_REQUEST_INFO,
    PERM_UPDATE,
    PERM_VET,
    assert_approval_authority,
    assert_can_act,
    assert_can_view,
    assert_dual_approval_ready,
    assert_fields_editable,
    assert_not_terminal,
    assert_segregation,
    assert_version,
    record_duty,
    validate_vetting_checklist,
)
from app.modules.claims.capabilities import compute_capabilities
from app.modules.claims.documents import (
    normalize_claim_storage_key,
    read_claim_document,
    store_claim_document,
)
from app.modules.claims.enums import (
    AmendmentStatus,
    AssignmentReason,
    BeneficiaryType,
    ClaimEventActorType,
    ClaimStatus,
    ClaimType,
    Duty,
    ExternalReviewProvider,
    ExternalReviewStatus,
    FollowupStatus,
    FollowupType,
    NoteVisibility,
    PaymentInstructionStatus,
    VettingDecision,
)
from app.modules.claims.events import ClaimEventService
from app.modules.claims.models import (
    Claim,
    ClaimAmendment,
    ClaimApproval,
    ClaimAssignment,
    ClaimDocument,
    ClaimDocumentAccess,
    ClaimExternalReview,
    ClaimFollowup,
    ClaimNote,
    ClaimPayment,
    ClaimVetting,
    ClaimWebhookReceipt,
)
from app.modules.claims.notify import notify_claim_event
from app.modules.claims.pdf import render_claim_pdf
from app.modules.files.enums import StoredFileAccessKind
from app.modules.files.registry import persist_mail_pdf
from app.modules.notifications.pdf_mail import enqueue_downloaded_pdf_emails
from app.modules.claims.projection import to_detail, to_list_item_named
from app.modules.claims.repository import ClaimChildRepository, ClaimRepository
from app.modules.claims.schemas import (
    ClaimAmendmentRequest,
    ClaimAmendmentReviewRequest,
    ClaimAssignRequest,
    ClaimCreateRequest,
    ClaimFollowupCreateRequest,
    ClaimHandoffTask,
    ClaimInsurerDecisionRequest,
    ClaimNoteRequest,
    ClaimSettlementRequest,
    ClaimUpdateRequest,
    ClaimVetRequest,
)
from app.modules.claims.workflow import assert_transition
from app.modules.customers.models import Customer
from app.modules.notifications.enums import NotificationTemplate
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.models import Policy
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.tenants.models import Tenant
from app.modules.users.models import User


def _now() -> datetime:
    return datetime.now(UTC)


def _claim_number() -> str:
    year = datetime.now(UTC).year
    return f"CLM-{year}-{secrets.token_hex(4).upper()}"


class ClaimService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = ClaimRepository(session, ctx)
        self.children = ClaimChildRepository(session, ctx)
        self.events = ClaimEventService(session, ctx)

    def _client_notice(self, claim: Claim, body: str) -> None:
        text = " ".join((body or "").split()).strip()
        if len(text) < 3:
            return
        self.session.add(
            ClaimNote(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                visibility=NoteVisibility.CLIENT.value,
                body=text[:2000],
                created_by_user_id=self.ctx.actor_user_id,
            )
        )

    async def dashboard(self) -> dict[str, Any]:
        self.ctx.require_permission("claim:read")
        stats = await self.repo.desk_stats()
        queues = []
        if self.ctx.allows(PERM_VET) or self.ctx.allows(PERM_ASSIGN):
            queues.append("intake")
        if self.ctx.allows(PERM_VET):
            queues.append("vetting")
        if self.ctx.allows(PERM_REQUEST_INFO):
            queues.append("information")
        if self.ctx.allows(PERM_APPROVE):
            queues.append("approval")
            queues.append("high_value")
        if self.ctx.allows(PERM_FORWARD):
            queues.append("definite")
        if self.ctx.allows(PERM_PAY_READ):
            queues.append("payment")
            queues.append("payment_failed")
        queue_counts = {queue: int(stats["queue_counts"].get(queue, 0)) for queue in queues}
        return {
            "role_code": self.ctx.role_code,
            "status_counts": stats["status_counts"],
            "assigned": [],
            "assigned_total": int(stats["assigned_total"]),
            "queues": {queue: [] for queue in queues},
            "queue_counts": queue_counts,
            "capabilities": {
                "can_create": self.ctx.allows(PERM_CREATE),
                "can_supervise": self.ctx.allows("claim:supervise"),
                "can_manage_policies": self.ctx.allows("claim:override_workflow"),
            },
        }

    async def list(
        self,
        *,
        page: int,
        limit: int,
        query: str | None,
        status: str | None,
        assigned_to_me: bool,
        queue: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        self.ctx.require_permission("claim:read")
        rows, total = await self.repo.search_listed(
            query=query,
            status=status,
            assigned_to_me=assigned_to_me,
            queue=queue,
            offset=(page - 1) * limit,
            limit=limit,
        )
        return [
            to_list_item_named(
                self.ctx,
                claim,
                customer_name=customer_name,
                agency_name=agency_name,
                assigned_to_name=assigned_to_name,
            )
            for claim, customer_name, agency_name, assigned_to_name in rows
        ], total

    async def get(self, claim_id: UUID) -> dict[str, Any]:
        claim = await self.repo.get(claim_id)
        assert_can_view(self.ctx, claim)
        return await self.present(claim)

    async def render_file_pdf(
        self,
        claim: Claim,
        *,
        generated_by: str | None = None,
        generated_by_role: str | None = None,
    ) -> tuple[bytes, str]:
        """Build the branded claim PDF. Caller is responsible for authorization."""
        payload = await self.present(claim)
        tenant = await self.session.get(Tenant, claim.tenant_id)
        letterhead = {
            "agency": (
                (tenant.trading_name or tenant.legal_name) if tenant else payload.get("agency_name")
            ),
            "legal_name": getattr(tenant, "legal_name", None),
            "phone": getattr(tenant, "phone", None),
            "email": getattr(tenant, "email", None),
            "generated_by": generated_by or self.ctx.actor_display_name or self.ctx.email,
            "generated_by_role": generated_by_role or self.ctx.role_code,
        }
        content = render_claim_pdf(payload, letterhead=letterhead)
        filename = f"{claim.claim_number or 'claim'}.pdf"
        return content, filename

    async def download_pdf(
        self,
        claim_id: UUID,
        *,
        disposition: str = "inline",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bytes, str]:
        claim = await self.repo.get(claim_id)
        assert_can_view(self.ctx, claim)
        content, filename = await self.render_file_pdf(claim)
        opened = disposition != "attachment"
        action = "CLAIM_PDF_OPENED" if opened else "CLAIM_PDF_DOWNLOADED"
        summary = (
            f"Opened claim file {claim.claim_number}"
            if opened
            else f"Downloaded claim file {claim.claim_number}"
        )
        await self.events.record(
            claim_id=claim.id,
            action=action,
            summary=summary,
            metadata={"disposition": "inline" if opened else "attachment"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        try:
            await persist_mail_pdf(
                self.session,
                self.ctx,
                kind="claim",
                resource_id=claim.id,
                content=content,
                filename=filename,
                access_kind=(
                    StoredFileAccessKind.VIEW.value
                    if opened
                    else StoredFileAccessKind.DOWNLOAD.value
                ),
                customer_id=claim.customer_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception:
            from app.core.logging import get_logger

            get_logger(__name__).warning(
                "claim_pdf_registry_failed",
                extra={"claim_id": str(claim.id)},
                exc_info=True,
            )
        if not opened:
            await enqueue_downloaded_pdf_emails(
                self.session,
                self.ctx,
                kind="claim",
                resource_id=claim.id,
                customer_id=claim.customer_id,
                content=content,
                filename=filename,
                context={
                    "claim_id": str(claim.id),
                    "claim_number": claim.claim_number,
                    "vehicle_registration": claim.vehicle_registration or "",
                    "status": claim.status,
                },
                already_stored=True,
            )
        return content, filename

    async def record_view(
        self,
        claim_id: UUID,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_view(self.ctx, claim)
        recent = await self.children.latest_actor_action(
            claim.id,
            action="CLAIM_OPENED",
            user_id=self.ctx.actor_user_id,
        )
        opened_at = getattr(recent, "created_at", None)
        if recent is not None and opened_at is not None:
            stamp = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
            if _now() - stamp < timedelta(seconds=30):
                return claim
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_OPENED",
            summary=f"Viewed claim {claim.claim_number}",
            metadata={"kind": "file"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return claim

    async def present(self, claim: Claim) -> dict[str, Any]:
        """Build the desk payload from an already-authorized claim row."""
        return await self._detail(claim)

    async def create(self, body: ClaimCreateRequest) -> Claim:
        self.ctx.require_permission(PERM_CREATE)
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        if body.claim_type not in {item.value for item in ClaimType}:
            raise ValidationAppError("Unsupported claim type")
        if body.beneficiary_type not in {item.value for item in BeneficiaryType}:
            raise ValidationAppError("Unsupported beneficiary")
        policy = await self.session.get(Policy, body.policy_id)
        if policy is None or policy.tenant_id != self.ctx.tenant_id:
            raise ResourceNotFoundError()
        if self.ctx.is_sales_agent and (
            self.ctx.agent_intermediary_id is None
            or policy.intermediary_id != self.ctx.agent_intermediary_id
        ):
            raise ResourceNotFoundError()
        self.ctx.assert_branch_access(policy.branch_id)
        if policy.status != PolicyStatus.ACTIVE.value:
            raise ValidationAppError("Claims can only be opened against an active policy")
        customer = await self.session.get(Customer, policy.customer_id)
        if customer is None or customer.tenant_id != self.ctx.tenant_id:
            raise ResourceNotFoundError()
        claim = Claim(
            tenant_id=self.ctx.tenant_id,
            branch_id=policy.branch_id,
            customer_id=policy.customer_id,
            policy_id=policy.id,
            created_by_user_id=self.ctx.user_id,
            assigned_to_user_id=self.ctx.user_id,
            claim_number=_claim_number(),
            claim_type=body.claim_type,
            incident_date=body.incident_date,
            incident_time=body.incident_time,
            incident_location=body.incident_location,
            incident_description=body.incident_description,
            police_abstract_number=body.police_abstract_number,
            vehicle_registration=policy.vehicle_registration,
            vehicle_make=policy.vehicle_make,
            vehicle_model=policy.vehicle_model,
            chassis_number=policy.chassis_number,
            driver_name=body.driver_name,
            driver_license_number=body.driver_license_number,
            damage_description=body.damage_description,
            injury_summary=body.injury_summary,
            claimed_amount=body.claimed_amount,
            currency="KES",
            beneficiary_type=body.beneficiary_type,
            beneficiary_reference=body.beneficiary_reference or customer.phone,
        )
        await self.repo.add(claim)
        await self.session.flush()
        await self._assign(
            claim,
            assigned_to=self.ctx.user_id,
            reason=AssignmentReason.CREATED.value,
            note="Opened by reporter",
            is_new=True,
        )
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_CREATED",
            summary=f"Opened claim {claim.claim_number}",
            new_state=claim.status,
            metadata={"policy_id": str(policy.id), "claimed_amount": str(body.claimed_amount)},
        )
        return claim

    async def update(self, claim_id: UUID, body: ClaimUpdateRequest) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_UPDATE)
        assert_not_terminal(claim)
        assert_version(claim, body.version)
        changes = body.model_dump(exclude_unset=True)
        changes.pop("version", None)
        assert_fields_editable(claim, set(changes))
        if "beneficiary_type" in changes and changes["beneficiary_type"] not in {
            item.value for item in BeneficiaryType
        }:
            raise ValidationAppError("Unsupported beneficiary")
        previous = {field: getattr(claim, field) for field in changes}
        for field, value in changes.items():
            setattr(claim, field, value)
        self._bump(claim)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_EDITED",
            summary="Updated claim details",
            metadata={"fields": sorted(changes), "previous": {k: str(v) for k, v in previous.items()}},
        )
        return claim

    async def submit(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_UPDATE)
        assert_version(claim, version)
        if not claim.incident_date or not claim.incident_description:
            raise ValidationAppError("Incident date and description are required to submit")
        await self._transition(claim, ClaimStatus.CLAIM_SUBMITTED.value)
        claim.submitted_at = _now()
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_SUBMITTED",
            summary="Submitted claim for vetting",
            previous_state=ClaimStatus.CLAIM_DRAFT.value,
            new_state=claim.status,
        )
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_RECEIVED.value,
        )
        return claim

    async def list_assignees(self, claim_id: UUID) -> list[dict[str, str]]:
        """Staff on this claim's tenant who can own the file."""
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_ASSIGN, require_assignment=False)
        claim_roles = select(RolePermission.role_id).join(
            Permission, Permission.id == RolePermission.permission_id
        ).where(
            Permission.code.in_(
                ("claim:read", "claim:vet", "claim:assign", "claim:supervise")
            )
        )
        rows = (
            await self.session.execute(
                select(User, Role)
                .outerjoin(Role, Role.id == User.role_id)
                .where(
                    User.tenant_id == claim.tenant_id,
                    User.deleted_at.is_(None),
                    User.status == UserStatus.ACTIVE.value,
                    or_(
                        User.is_platform_admin.is_(True),
                        User.role_id.in_(claim_roles),
                    ),
                )
                .order_by(User.full_name.asc())
            )
        ).all()
        return [
            {
                "id": str(user.id),
                "name": user.full_name,
                "role": (role.name if role is not None else "Staff"),
            }
            for user, role in rows
        ]

    async def assign(self, claim_id: UUID, body: ClaimAssignRequest) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_ASSIGN, require_assignment=False)
        assert_version(claim, body.version)
        user = await self.session.get(User, body.assigned_to_user_id)
        if user is None or user.deleted_at is not None or user.tenant_id != claim.tenant_id:
            raise ValidationAppError("Assignee is not a member of this organization")
        await self._assign(
            claim,
            assigned_to=user.id,
            reason=body.reason if body.reason in {item.value for item in AssignmentReason} else AssignmentReason.MANUAL.value,
            note=body.note,
        )
        self._bump(claim)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_ASSIGNED",
            summary=f"Assigned claim to {user.full_name}",
            metadata={"assigned_to": str(user.id)},
        )
        await self._attach_handoff_task(claim, body.task, assigned_to=user.id)
        return claim

    async def start_vetting(
        self,
        claim_id: UUID,
        *,
        version: int,
        task: ClaimHandoffTask | None = None,
    ) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_VET)
        assert_version(claim, version)
        previous = claim.status
        if claim.status == ClaimStatus.CLAIM_SUBMITTED.value:
            await self._transition(claim, ClaimStatus.VETTING.value)
        elif claim.status != ClaimStatus.VETTING.value:
            raise ConflictError("Claim is not ready for vetting")
        current = await self.children.current_vetting(claim.id)
        if current is None or current.completed_at is not None:
            if current is not None:
                current.is_current = False
            self.session.add(
                ClaimVetting(
                    tenant_id=claim.tenant_id,
                    claim_id=claim.id,
                    assigned_to_user_id=self.ctx.user_id,
                    created_by_user_id=self.ctx.user_id,
                    started_at=_now(),
                    is_current=True,
                )
            )
        for row in await self.children.open_followups(claim.id):
            if row.subject == "Guest claim awaiting assignment":
                row.status = FollowupStatus.COMPLETED.value
                row.completed_at = _now()
        await self.events.record(
            claim_id=claim.id,
            action="VETTING_STARTED",
            summary="Started vetting",
            previous_state=previous,
            new_state=claim.status,
            tenant_id=claim.tenant_id,
        )
        self._client_notice(claim, "The agency has started reviewing your claim.")
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_UNDER_REVIEW.value,
        )
        await self._attach_handoff_task(
            claim,
            task,
            assigned_to=claim.assigned_to_user_id or self.ctx.user_id,
        )
        return claim

    async def complete_vetting(self, claim_id: UUID, body: ClaimVetRequest) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_VET)
        assert_version(claim, body.version)
        if claim.status != ClaimStatus.VETTING.value:
            raise ConflictError("Claim is not in vetting")
        decision = body.decision.upper()
        if decision not in {item.value for item in VettingDecision}:
            raise ValidationAppError("Unsupported vetting decision")
        validate_vetting_checklist(body.checklist, decision=decision)
        open_followups = await self.children.open_followups(claim.id)
        for row in open_followups:
            if row.subject == "Guest claim awaiting assignment":
                row.status = FollowupStatus.COMPLETED.value
                row.completed_at = _now()
        await self.session.flush()
        if decision == VettingDecision.PASS.value:
            remaining = [
                row
                for row in open_followups
                if row.status
                in {
                    FollowupStatus.OPEN.value,
                    FollowupStatus.PENDING_CLIENT.value,
                    FollowupStatus.PENDING_INTERNAL.value,
                }
            ]
            if remaining:
                raise ValidationAppError("Close or cancel open follow-ups before passing vetting")
        await assert_segregation(self.session, self.ctx, claim_id=claim.id, duty=Duty.VET.value)
        vetting = await self.children.current_vetting(claim.id)
        if vetting is None:
            vetting = ClaimVetting(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                assigned_to_user_id=self.ctx.user_id,
                created_by_user_id=self.ctx.user_id,
                started_at=_now(),
                is_current=True,
            )
            self.session.add(vetting)
        vetting.updated_by_user_id = self.ctx.user_id
        vetting.completed_at = _now()
        vetting.decision = decision
        vetting.decision_reason = body.decision_reason
        vetting.findings = body.findings
        vetting.required_documents = body.required_documents
        vetting.checklist = body.checklist
        previous = claim.status
        if decision == VettingDecision.PASS.value:
            await self._transition(claim, ClaimStatus.VETTING_PASSED.value)
            action = "VETTING_PASSED"
            summary = "Completed vetting — PASS"
        elif decision == VettingDecision.FAIL.value:
            await self._transition(claim, ClaimStatus.VETTING_FAILED.value)
            action = "VETTING_FAILED"
            summary = "Completed vetting — FAIL"
        else:
            await self._transition(claim, ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value)
            action = "VETTING_COMPLETED"
            summary = "Requested additional information"
        await record_duty(
            self.session,
            tenant_id=claim.tenant_id,
            claim_id=claim.id,
            duty=Duty.VET.value,
            user_id=self.ctx.user_id,
        )
        await self.events.record(
            claim_id=claim.id,
            action=action,
            summary=summary,
            previous_state=previous,
            new_state=claim.status,
            metadata={"decision": decision},
            tenant_id=claim.tenant_id,
        )
        if decision == VettingDecision.PASS.value:
            self._client_notice(
                claim,
                "The agency has finished their review and is sending your claim to the insurer.",
            )
        elif decision == VettingDecision.FAIL.value:
            self._client_notice(claim, "The agency was not able to approve this claim.")
        else:
            self._client_notice(
                claim,
                f"The agency needs a little more from you. {body.decision_reason.strip()}",
            )
        template = {
            VettingDecision.PASS.value: NotificationTemplate.CLAIM_VETTING_PASSED.value,
            VettingDecision.FAIL.value: NotificationTemplate.CLAIM_REJECTED.value,
            VettingDecision.MORE_INFORMATION_REQUIRED.value: NotificationTemplate.CLAIM_INFORMATION_REQUIRED.value,
        }[decision]
        await notify_claim_event(self.session, self.ctx, claim=claim, template=template)
        return claim

    async def request_information(self, claim_id: UUID, *, version: int, reason: str) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_REQUEST_INFO)
        assert_version(claim, version)
        previous = claim.status
        await self._transition(claim, ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value)
        await self.events.record(
            claim_id=claim.id,
            action="FOLLOWUP_CREATED",
            summary="Requested additional information",
            previous_state=previous,
            new_state=claim.status,
            metadata={"reason": reason},
        )
        self._client_notice(
            claim,
            f"The agency needs a little more from you. {reason.strip()}",
        )
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_INFORMATION_REQUIRED.value,
        )
        return claim

    async def resume_vetting(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_VET)
        assert_version(claim, version)
        previous = claim.status
        await self._transition(claim, ClaimStatus.VETTING.value)
        await self.events.record(
            claim_id=claim.id,
            action="VETTING_STARTED",
            summary="Resumed vetting after information received",
            previous_state=previous,
            new_state=claim.status,
        )
        self._client_notice(claim, "The agency has resumed review of your claim.")
        return claim

    async def forward_to_definite(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_FORWARD)
        assert_version(claim, version)
        vetting = await self.children.current_vetting(claim.id)
        if (
            vetting is None
            or vetting.decision != VettingDecision.PASS.value
            or claim.status != ClaimStatus.VETTING_PASSED.value
        ):
            raise ConflictError("A passed vetting record is required before forwarding")
        validate_vetting_checklist(vetting.checklist or {}, decision=VettingDecision.PASS.value)
        previous = claim.status
        await self._transition(claim, ClaimStatus.SENT_TO_DEFINITE.value)
        reference = f"DEF-{secrets.token_hex(5).upper()}"
        self.session.add(
            ClaimExternalReview(
                tenant_id=self.ctx.tenant_id,
                claim_id=claim.id,
                provider=ExternalReviewProvider.DEFINITE.value,
                external_reference=reference,
                submitted_at=_now(),
                submitted_by_user_id=self.ctx.user_id,
                status=ExternalReviewStatus.SUBMITTED.value,
            )
        )
        await self._transition(claim, ClaimStatus.DEFINITE_REVIEW.value, system=True)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_FORWARDED_TO_DEFINITE",
            summary="Claim forwarded to Definite",
            previous_state=previous,
            new_state=claim.status,
            actor_type=ClaimEventActorType.SYSTEM.value,
            metadata={"external_reference": reference},
        )
        self._client_notice(claim, "Your claim has been sent to the insurer.")
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_FORWARDED.value,
        )
        return claim

    async def record_insurer_decision(
        self, claim_id: UUID, body: ClaimInsurerDecisionRequest
    ) -> Claim:
        """Officer records a decision the insurer made outside Star Serve."""
        claim = await self._locked(claim_id)
        if self.ctx.allows(PERM_FORWARD):
            assert_can_act(self.ctx, claim, PERM_FORWARD, require_assignment=False)
        elif self.ctx.allows(PERM_APPROVE):
            assert_can_act(self.ctx, claim, PERM_APPROVE, require_assignment=False)
        else:
            raise AuthorizationError("You cannot record the insurer decision on this claim")
        assert_version(claim, body.version)
        if claim.status not in {
            ClaimStatus.SENT_TO_DEFINITE.value,
            ClaimStatus.DEFINITE_REVIEW.value,
        }:
            raise ConflictError("The insurer decision can only be recorded while the file is with them")
        decision = body.decision.upper()
        if body.beneficiary_type:
            self._set_payee(claim, body.beneficiary_type)
        review = await self.children.latest_review(claim.id)
        if review is None:
            review = ClaimExternalReview(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                provider=ExternalReviewProvider.DEFINITE.value,
                external_reference=f"DEF-{secrets.token_hex(5).upper()}",
                submitted_at=_now(),
                submitted_by_user_id=self.ctx.user_id,
                status=ExternalReviewStatus.SUBMITTED.value,
            )
            self.session.add(review)
        if claim.status == ClaimStatus.SENT_TO_DEFINITE.value:
            await self._transition(claim, ClaimStatus.DEFINITE_REVIEW.value, system=True)
        previous = claim.status
        if decision == "APPROVED":
            amount = body.approved_amount if body.approved_amount is not None else claim.claimed_amount
            if amount is None or amount <= 0:
                raise ValidationAppError("Enter the amount the insurer approved")
            review.status = ExternalReviewStatus.APPROVED.value
            review.decision = "APPROVED"
            review.approved_amount = amount
            claim.approved_amount = amount
            await self._transition(claim, ClaimStatus.DEFINITE_APPROVED.value, system=True)
            await self._transition(claim, ClaimStatus.PAYMENT_PENDING.value, system=True)
            action = "CLAIM_APPROVED"
            summary = f"Recorded insurer approval of {claim.currency} {amount}"
            if claim.beneficiary_type == BeneficiaryType.STAR_SERVE.value:
                notice = (
                    "The insurer has approved your claim. They will pay the agency, "
                    "who will then pay you."
                )
            else:
                notice = "The insurer has approved your claim. They will pay you directly."
            template = NotificationTemplate.CLAIM_APPROVED.value
        else:
            reason = (body.reason or "").strip()
            if len(reason) < 3:
                raise ValidationAppError("Add a short note from the insurer before declining")
            review.status = ExternalReviewStatus.REJECTED.value
            review.decision = "REJECTED"
            await self._transition(claim, ClaimStatus.DEFINITE_REJECTED.value, system=True)
            action = "CLAIM_REJECTED"
            summary = "Recorded insurer decline"
            notice = "The insurer has declined this claim."
            template = NotificationTemplate.CLAIM_REJECTED.value
        review.response_received_at = _now()
        await self.events.record(
            claim_id=claim.id,
            action=action,
            summary=summary,
            previous_state=previous,
            new_state=claim.status,
            metadata={
                "source": "OFFICER",
                "decision": decision,
                "pay_to": claim.beneficiary_type,
                "reason": (body.reason or "").strip() or None,
            },
        )
        self._client_notice(claim, notice)
        await notify_claim_event(self.session, self.ctx, claim=claim, template=template)
        return claim

    async def record_settlement(self, claim_id: UUID, body: ClaimSettlementRequest) -> Claim:
        """Confirm an off-system payout — insurer-to-client or agency-to-client."""
        claim = await self._locked(claim_id)
        if self.ctx.allows(PERM_FORWARD):
            assert_can_act(self.ctx, claim, PERM_FORWARD, require_assignment=False)
        elif self.ctx.allows(PERM_APPROVE):
            assert_can_act(self.ctx, claim, PERM_APPROVE, require_assignment=False)
        elif self.ctx.allows(PERM_PAY_AUTH):
            assert_can_view(self.ctx, claim)
        else:
            raise AuthorizationError("You cannot record settlement on this claim")
        assert_version(claim, body.version)
        if claim.status not in {
            ClaimStatus.DEFINITE_APPROVED.value,
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.PAYMENT_AUTHORIZED.value,
            ClaimStatus.PAYMENT_PROCESSING.value,
            ClaimStatus.PAYMENT_FAILED.value,
            ClaimStatus.PAYMENT_REVIEW.value,
        }:
            raise ConflictError("Settlement can only be recorded after the insurer has approved")
        if body.beneficiary_type:
            self._set_payee(claim, body.beneficiary_type)
        if claim.approved_amount is None:
            claim.approved_amount = claim.claimed_amount
        if claim.approved_amount is None or claim.approved_amount <= 0:
            raise ValidationAppError("Approved amount must be greater than zero")
        previous = claim.status
        if claim.status == ClaimStatus.DEFINITE_APPROVED.value:
            await self._transition(claim, ClaimStatus.PAYMENT_PENDING.value)
        if claim.status == ClaimStatus.PAYMENT_FAILED.value:
            await self._transition(claim, ClaimStatus.PAYMENT_REVIEW.value)
        if claim.status in {
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.PAYMENT_REVIEW.value,
        }:
            await self._transition(claim, ClaimStatus.PAYMENT_AUTHORIZATION.value)
        if claim.status == ClaimStatus.PAYMENT_AUTHORIZATION.value:
            await self._transition(claim, ClaimStatus.PAYMENT_AUTHORIZED.value)
        payment = await self.children.active_payment(claim.id)
        if payment is None:
            payment = ClaimPayment(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                branch_id=claim.branch_id,
                beneficiary_type=claim.beneficiary_type,
                beneficiary_reference=claim.beneficiary_reference,
                amount=claim.approved_amount,
                currency=claim.currency,
                payment_status=PaymentInstructionStatus.PROCESSING.value,
                provider="OFF_SYSTEM",
                provider_reference=(body.reference or "").strip() or f"SET-{secrets.token_hex(6).upper()}",
                idempotency_key=f"set-{claim.id}-{uuid4().hex[:12]}",
                initiated_at=_now(),
            )
            self.session.add(payment)
        else:
            payment.beneficiary_type = claim.beneficiary_type
            payment.beneficiary_reference = claim.beneficiary_reference
            payment.amount = claim.approved_amount
            payment.provider = payment.provider or "OFF_SYSTEM"
            if body.reference:
                payment.provider_reference = body.reference.strip()
            elif not payment.provider_reference:
                payment.provider_reference = f"SET-{secrets.token_hex(6).upper()}"
        if claim.status == ClaimStatus.PAYMENT_AUTHORIZED.value:
            await self._transition(claim, ClaimStatus.PAYMENT_PROCESSING.value)
        if claim.status != ClaimStatus.PAYMENT_PROCESSING.value:
            raise ConflictError("Claim is not ready to record settlement")
        payment.payment_status = PaymentInstructionStatus.COMPLETED.value
        payment.completed_at = _now()
        payment.executed_by_user_id = payment.executed_by_user_id or self.ctx.user_id
        await self._transition(claim, ClaimStatus.PAYMENT_COMPLETED.value, system=True)
        await self._transition(claim, ClaimStatus.CLIENT_NOTIFIED.value, system=True)
        if claim.beneficiary_type == BeneficiaryType.STAR_SERVE.value:
            notice = "The agency has paid you the approved settlement."
            summary = "Recorded agency payout to the client"
        else:
            notice = "The insurer has paid you directly."
            summary = "Recorded insurer payout to the client"
        if body.note:
            summary = f"{summary} — {body.note.strip()}"
        await self.events.record(
            claim_id=claim.id,
            action="PAYMENT_COMPLETED",
            summary=summary[:500],
            previous_state=previous,
            new_state=claim.status,
            metadata={
                "source": "OFFICER",
                "pay_to": claim.beneficiary_type,
                "reference": payment.provider_reference,
            },
        )
        self._client_notice(claim, notice)
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_PAYMENT_COMPLETED.value,
        )
        return claim

    async def apply_definite_decision(
        self,
        *,
        external_reference: str,
        decision: str,
        approved_amount: Decimal | None,
        payload_reference: str,
    ) -> Claim:
        review = await self.children.review_by_reference(
            provider=ExternalReviewProvider.DEFINITE.value,
            external_reference=external_reference,
        )
        if review is None:
            raise ResourceNotFoundError()
        claim = await self.session.get(Claim, review.claim_id)
        if claim is None:
            raise ResourceNotFoundError()
        self.ctx.tenant_id = claim.tenant_id  # type: ignore[misc]
        if review.status in {
            ExternalReviewStatus.APPROVED.value,
            ExternalReviewStatus.REJECTED.value,
        }:
            return claim
        normalized = decision.upper()
        previous = claim.status
        if normalized == "APPROVED":
            review.status = ExternalReviewStatus.APPROVED.value
            review.decision = "APPROVED"
            review.approved_amount = approved_amount or claim.claimed_amount
            claim.approved_amount = review.approved_amount
            await self._transition(claim, ClaimStatus.DEFINITE_APPROVED.value, system=True)
            await self._transition(claim, ClaimStatus.PAYMENT_PENDING.value, system=True)
            action = "CLAIM_APPROVED"
            summary = "Definite approved the claim"
        elif normalized == "REJECTED":
            review.status = ExternalReviewStatus.REJECTED.value
            review.decision = "REJECTED"
            await self._transition(claim, ClaimStatus.DEFINITE_REJECTED.value, system=True)
            action = "CLAIM_REJECTED"
            summary = "Definite rejected the claim"
        else:
            raise ValidationAppError("Unsupported Definite decision")
        review.response_received_at = _now()
        review.response_payload_reference = payload_reference
        await self.events.record(
            claim_id=claim.id,
            action="DEFINITE_RESPONSE_RECEIVED",
            summary=summary,
            previous_state=previous,
            new_state=claim.status,
            actor_type=ClaimEventActorType.DEFINITE.value,
            actor_display_name="Definite",
            metadata={"external_reference": external_reference, "decision": normalized},
        )
        template = (
            NotificationTemplate.CLAIM_APPROVED.value
            if normalized == "APPROVED"
            else NotificationTemplate.CLAIM_REJECTED.value
        )
        await notify_claim_event(self.session, self.ctx, claim=claim, template=template)
        return claim

    async def approve(self, claim_id: UUID, *, version: int, reason: str | None) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_APPROVE)
        assert_version(claim, version)
        if claim.status != ClaimStatus.VETTING_PASSED.value:
            raise ConflictError("Internal approval is only available after vetting has passed")
        amount = claim.claimed_amount
        policy = await assert_approval_authority(
            self.session, self.ctx, claim=claim, amount=amount
        )
        await assert_segregation(self.session, self.ctx, claim_id=claim.id, duty=Duty.APPROVE.value)
        complete = await assert_dual_approval_ready(
            self.session, self.ctx, claim=claim, policy=policy, amount=amount
        )
        existing = await self.children.approvals(claim.id)
        sequence = len([row for row in existing if not row.superseded]) + 1
        self.session.add(
            ClaimApproval(
                tenant_id=self.ctx.tenant_id,
                claim_id=claim.id,
                approver_user_id=self.ctx.user_id,
                decision="APPROVED",
                amount=amount,
                sequence=sequence,
                reason=reason,
            )
        )
        await record_duty(
            self.session,
            tenant_id=self.ctx.tenant_id,
            claim_id=claim.id,
            duty=Duty.APPROVE.value,
            user_id=self.ctx.user_id,
        )
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_APPROVED",
            summary=f"Recorded approval {sequence} for {claim.currency} {amount}",
            metadata={"sequence": sequence, "complete": complete},
        )
        if complete:
            self._client_notice(claim, "The agency has approved your claim.")
        return claim

    async def reject(self, claim_id: UUID, *, version: int, reason: str) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_REJECT)
        assert_version(claim, version)
        previous = claim.status
        await self._transition(claim, ClaimStatus.REJECTED.value)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_REJECTED",
            summary="Rejected claim",
            previous_state=previous,
            new_state=claim.status,
            metadata={"reason": reason},
        )
        self._client_notice(claim, "The agency has declined this claim.")
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_REJECTED.value,
        )
        return claim

    async def withdraw(self, claim_id: UUID, *, version: int, reason: str) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_UPDATE)
        assert_version(claim, version)
        previous = claim.status
        await self._transition(claim, ClaimStatus.WITHDRAWN.value)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_EDITED",
            summary="Withdrew claim",
            previous_state=previous,
            new_state=claim.status,
            metadata={"reason": reason},
        )
        return claim

    async def request_payment(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_PAY_AUTH, require_assignment=False)
        assert_version(claim, version)
        if claim.status != ClaimStatus.PAYMENT_PENDING.value:
            raise ConflictError("Payment can only be requested after Definite approval")
        if claim.approved_amount is None:
            raise ConflictError("Approved amount has not been set by Definite")
        previous = claim.status
        await self._transition(claim, ClaimStatus.PAYMENT_AUTHORIZATION.value)
        payment = await self.children.active_payment(claim.id)
        if payment is None:
            self.session.add(
                ClaimPayment(
                    tenant_id=self.ctx.tenant_id,
                    claim_id=claim.id,
                    branch_id=claim.branch_id,
                    beneficiary_type=claim.beneficiary_type,
                    beneficiary_reference=claim.beneficiary_reference,
                    amount=claim.approved_amount,
                    currency=claim.currency,
                    payment_status=PaymentInstructionStatus.PENDING_AUTHORIZATION.value,
                    idempotency_key=f"pay-{claim.id}-{uuid4().hex[:12]}",
                )
            )
        await self.events.record(
            claim_id=claim.id,
            action="PAYMENT_INITIATED",
            summary="Payment instruction raised for authorization",
            previous_state=previous,
            new_state=claim.status,
        )
        return claim

    async def authorize_payment(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_PAY_AUTH, require_assignment=False)
        assert_version(claim, version)
        if claim.status not in {
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.PAYMENT_REVIEW.value,
        }:
            raise ConflictError("Claim is not awaiting payment authorization")
        await assert_segregation(
            self.session, self.ctx, claim_id=claim.id, duty=Duty.AUTHORIZE_PAYMENT.value
        )
        payment = await self.children.active_payment(claim.id)
        if payment is None:
            raise ConflictError("No payment instruction exists")
        if payment.beneficiary_type != claim.beneficiary_type:
            raise ConflictError("Beneficiary changed after the instruction was created")
        payment.authorized_by_user_id = self.ctx.user_id
        payment.authorized_at = _now()
        payment.payment_status = PaymentInstructionStatus.AUTHORIZED.value
        previous = claim.status
        await self._transition(claim, ClaimStatus.PAYMENT_AUTHORIZED.value)
        await record_duty(
            self.session,
            tenant_id=self.ctx.tenant_id,
            claim_id=claim.id,
            duty=Duty.AUTHORIZE_PAYMENT.value,
            user_id=self.ctx.user_id,
        )
        await self.events.record(
            claim_id=claim.id,
            action="PAYMENT_AUTHORIZED",
            summary=f"Payment authorized {claim.currency} {payment.amount}",
            previous_state=previous,
            new_state=claim.status,
            metadata={"amount": str(payment.amount)},
        )
        return claim

    async def execute_payment(self, claim_id: UUID, *, version: int, idempotency_key: str) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_PAY_EXEC, require_assignment=False)
        assert_version(claim, version)
        if claim.status != ClaimStatus.PAYMENT_AUTHORIZED.value:
            raise ConflictError("Payment has not been authorized")
        await assert_segregation(
            self.session, self.ctx, claim_id=claim.id, duty=Duty.EXECUTE_PAYMENT.value
        )
        existing = await self.children.payment_by_idempotency(idempotency_key)
        if existing is not None:
            return claim
        payment = await self.children.active_payment(claim.id)
        if payment is None:
            raise ConflictError("No authorized payment instruction exists")
        if payment.payment_status == PaymentInstructionStatus.PROCESSING.value:
            return claim
        if payment.authorized_by_user_id == self.ctx.user_id:
            raise AuthorizationError("The authorizer cannot execute the same payment")
        payment.idempotency_key = idempotency_key
        payment.executed_by_user_id = self.ctx.user_id
        payment.initiated_at = _now()
        payment.payment_status = PaymentInstructionStatus.PROCESSING.value
        payment.provider = "CLAIM_PAYOUT"
        payment.provider_reference = f"PO-{secrets.token_hex(8).upper()}"
        previous = claim.status
        await self._transition(claim, ClaimStatus.PAYMENT_PROCESSING.value)
        await record_duty(
            self.session,
            tenant_id=self.ctx.tenant_id,
            claim_id=claim.id,
            duty=Duty.EXECUTE_PAYMENT.value,
            user_id=self.ctx.user_id,
        )
        await self.events.record(
            claim_id=claim.id,
            action="PAYMENT_INITIATED",
            summary="Payment submitted to provider",
            previous_state=previous,
            new_state=claim.status,
            metadata={"provider_reference": payment.provider_reference},
        )
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_PAYMENT_INITIATED.value,
        )
        return claim

    async def apply_payment_outcome(
        self,
        *,
        provider_reference: str,
        success: bool,
        failure_reason: str | None,
        payload_reference: str,
    ) -> Claim:
        payment = await self.children.payment_by_provider_reference(provider_reference)
        if payment is None:
            raise ResourceNotFoundError()
        claim = await self.session.get(Claim, payment.claim_id)
        if claim is None:
            raise ResourceNotFoundError()
        self.ctx.tenant_id = claim.tenant_id  # type: ignore[misc]
        if payment.payment_status == PaymentInstructionStatus.COMPLETED.value:
            return claim
        previous = claim.status
        if success:
            if claim.status != ClaimStatus.PAYMENT_PROCESSING.value:
                raise ConflictError("Claim is not awaiting a payment callback")
            payment.payment_status = PaymentInstructionStatus.COMPLETED.value
            payment.completed_at = _now()
            await self._transition(claim, ClaimStatus.PAYMENT_COMPLETED.value, system=True)
            await self._transition(claim, ClaimStatus.CLIENT_NOTIFIED.value, system=True)
            await self.events.record(
                claim_id=claim.id,
                action="PAYMENT_COMPLETED",
                summary="Payment completed",
                previous_state=previous,
                new_state=claim.status,
                actor_type=ClaimEventActorType.PAYMENT_PROVIDER.value,
                actor_display_name="Payment Service",
                metadata={"provider_reference": provider_reference, "receipt": payload_reference},
            )
            await notify_claim_event(
                self.session,
                self.ctx,
                claim=claim,
                template=NotificationTemplate.CLAIM_PAYMENT_COMPLETED.value,
            )
        else:
            payment.payment_status = PaymentInstructionStatus.FAILED.value
            payment.failure_reason = failure_reason
            await self._transition(claim, ClaimStatus.PAYMENT_FAILED.value, system=True)
            await self._transition(claim, ClaimStatus.PAYMENT_REVIEW.value, system=True)
            await self.events.record(
                claim_id=claim.id,
                action="PAYMENT_FAILED",
                summary="Payment failed",
                previous_state=previous,
                new_state=claim.status,
                actor_type=ClaimEventActorType.PAYMENT_PROVIDER.value,
                actor_display_name="Payment Service",
                metadata={"reason": failure_reason},
            )
        return claim

    async def retry_payment(self, claim_id: UUID, *, version: int, idempotency_key: str) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_PAY_RETRY, require_assignment=False)
        assert_version(claim, version)
        if claim.status not in {ClaimStatus.PAYMENT_FAILED.value, ClaimStatus.PAYMENT_REVIEW.value}:
            raise ConflictError("Payment cannot be retried in this state")
        if claim.status == ClaimStatus.PAYMENT_FAILED.value:
            await self._transition(claim, ClaimStatus.PAYMENT_REVIEW.value)
        await self._transition(claim, ClaimStatus.PAYMENT_AUTHORIZATION.value)
        return await self.authorize_payment(claim.id, version=claim.version)

    async def close(self, claim_id: UUID, *, version: int) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_CLOSE)
        assert_version(claim, version)
        previous = claim.status
        await self._transition(claim, ClaimStatus.CLOSED.value)
        claim.closed_at = _now()
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_CLOSED",
            summary="Closed claim",
            previous_state=previous,
            new_state=claim.status,
        )
        return claim

    async def add_note(self, claim_id: UUID, body: ClaimNoteRequest) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_NOTE_CREATE)
        self.session.add(
            ClaimNote(
                tenant_id=self.ctx.tenant_id,
                claim_id=claim.id,
                visibility=NoteVisibility.INTERNAL.value,
                body=body.body,
                created_by_user_id=self.ctx.user_id,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_EDITED",
            summary="Added an internal note",
        )
        await self.session.flush()
        return claim

    async def send_client_message(self, claim_id: UUID, *, subject: str, message: str) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_CLIENT_MESSAGE)
        self.session.add(
            ClaimNote(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                visibility=NoteVisibility.CLIENT.value,
                body=f"{subject}\n\n{message}",
                created_by_user_id=self.ctx.user_id,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="CLIENT_NOTIFIED",
            summary=subject,
        )
        await notify_claim_event(
            self.session,
            self.ctx,
            claim=claim,
            template=NotificationTemplate.CLAIM_CLIENT_MESSAGE.value,
        )
        await self.session.flush()
        return claim

    async def create_followup(
        self, claim_id: UUID, body: ClaimFollowupCreateRequest
    ) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_FOLLOWUP_CREATE)
        if body.followup_type not in {item.value for item in FollowupType}:
            raise ValidationAppError("Unsupported follow-up type")
        self.session.add(
            ClaimFollowup(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                followup_type=body.followup_type,
                subject=body.subject,
                message=body.message,
                requested_from=body.requested_from,
                due_at=body.due_at,
                status=FollowupStatus.OPEN.value,
                created_by_user_id=self.ctx.user_id,
                assigned_to_user_id=body.assigned_to_user_id or claim.assigned_to_user_id,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="FOLLOWUP_CREATED",
            summary=body.subject,
            metadata={"type": body.followup_type},
        )
        await self.session.flush()
        if body.followup_type in {
            FollowupType.CLIENT_INFORMATION.value,
            FollowupType.DOCUMENT_REQUIRED.value,
            FollowupType.MEDICAL_INFORMATION.value,
            FollowupType.POLICE_DOCUMENT.value,
            FollowupType.PAYMENT_INFORMATION.value,
        }:
            due = body.due_at.isoformat() if body.due_at else ""
            await notify_claim_event(
                self.session,
                self.ctx,
                claim=claim,
                template=NotificationTemplate.CLAIM_FOLLOWUP.value,
                extra={
                    "followup_subject": body.subject,
                    "detail": body.message,
                    "due_at": due,
                },
            )
        return claim

    async def complete_followup(self, claim_id: UUID, followup_id: UUID) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_FOLLOWUP_COMPLETE)
        row = await self.session.get(ClaimFollowup, followup_id)
        if row is None or row.claim_id != claim.id or row.tenant_id != claim.tenant_id:
            raise ResourceNotFoundError()
        row.status = FollowupStatus.COMPLETED.value
        row.completed_at = _now()
        row.completed_by_user_id = self.ctx.user_id
        await self.events.record(
            claim_id=claim.id,
            action="FOLLOWUP_COMPLETED",
            summary=row.subject,
            tenant_id=claim.tenant_id,
        )
        return claim

    async def request_amendment(self, claim_id: UUID, body: ClaimAmendmentRequest) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_APPROVE)
        assert_version(claim, body.version)
        existing = await self.children.open_amendment(claim.id)
        if existing is not None:
            raise ConflictError("An amendment is already under review")
        previous = getattr(claim, body.field_name)
        self.session.add(
            ClaimAmendment(
                tenant_id=self.ctx.tenant_id,
                claim_id=claim.id,
                requested_by_user_id=self.ctx.user_id,
                field_name=body.field_name,
                previous_value=str(previous) if previous is not None else None,
                proposed_value=body.proposed_value,
                status=AmendmentStatus.REQUESTED.value,
                reason=body.reason,
            )
        )
        for row in await self.children.approvals(claim.id):
            row.superseded = True
        self._bump(claim)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_EDITED",
            summary=f"Requested amendment to {body.field_name}",
            metadata={"field": body.field_name, "proposed": body.proposed_value},
        )
        return claim

    async def review_amendment(
        self, claim_id: UUID, amendment_id: UUID, body: ClaimAmendmentReviewRequest
    ) -> Claim:
        claim = await self._locked(claim_id)
        assert_can_act(self.ctx, claim, PERM_APPROVE)
        assert_version(claim, body.version)
        amendment = await self.session.get(ClaimAmendment, amendment_id)
        if amendment is None or amendment.claim_id != claim.id:
            raise ResourceNotFoundError()
        if amendment.requested_by_user_id == self.ctx.user_id:
            raise AuthorizationError("A different officer must review this amendment")
        amendment.status = body.decision
        amendment.reviewed_by_user_id = self.ctx.user_id
        amendment.reviewed_at = _now()
        amendment.reason = body.reason or amendment.reason
        if body.decision == AmendmentStatus.APPROVED.value:
            if amendment.field_name in {"claimed_amount", "approved_amount"}:
                setattr(claim, amendment.field_name, Decimal(amendment.proposed_value or "0"))
            else:
                setattr(claim, amendment.field_name, amendment.proposed_value)
        self._bump(claim)
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_EDITED",
            summary=f"Amendment {body.decision.lower()}",
            metadata={"field": amendment.field_name},
        )
        return claim

    async def upload_document(
        self,
        claim_id: UUID,
        *,
        kind: str,
        filename: str,
        payload: bytes,
        ip_address: str | None,
        user_agent: str | None,
    ) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_DOC_UPLOAD)
        # Hash first so we can reuse an existing blob + row without writing again.
        digest = hashlib.sha256(payload).hexdigest()
        existing = await self.children.document_by_sha256(claim.id, digest)
        if existing is not None:
            key = normalize_claim_storage_key(existing.storage_path)
            if get_blob_store().exists(namespace="claims/documents", relative_key=key):
                await self.events.record(
                    claim_id=claim.id,
                    action="DOCUMENT_UPLOADED",
                    summary=existing.original_filename,
                    metadata={
                        "kind": existing.kind,
                        "sha256": existing.content_sha256,
                        "reused": True,
                    },
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                return claim

        stored = await asyncio.to_thread(
            store_claim_document,
            tenant_id=self.ctx.tenant_id,
            claim_id=claim.id,
            payload=payload,
            filename=filename,
        )
        # Another concurrent upload may have created the row while we wrote.
        existing = await self.children.document_by_sha256(
            claim.id, str(stored["content_sha256"])
        )
        if existing is not None:
            await self.events.record(
                claim_id=claim.id,
                action="DOCUMENT_UPLOADED",
                summary=existing.original_filename,
                metadata={
                    "kind": existing.kind,
                    "sha256": existing.content_sha256,
                    "reused": True,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return claim

        document = ClaimDocument(
            tenant_id=self.ctx.tenant_id,
            claim_id=claim.id,
            uploaded_by_user_id=self.ctx.user_id,
            kind=kind,
            original_filename=str(stored["original_filename"]),
            stored_filename=str(stored["stored_filename"]),
            content_type=str(stored["content_type"]),
            content_sha256=str(stored["content_sha256"]),
            file_size_bytes=int(stored["file_size_bytes"]),
            storage_path=str(stored["storage_path"]),
        )
        self.session.add(document)
        await self.session.flush()
        await self.events.record(
            claim_id=claim.id,
            action="DOCUMENT_UPLOADED",
            summary=document.original_filename,
            metadata={
                "kind": kind,
                "sha256": document.content_sha256,
                "written": bool(stored.get("written", True)),
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return claim

    async def download_document(
        self,
        claim_id: UUID,
        document_id: UUID,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[ClaimDocument, bytes]:
        claim = await self.repo.get(claim_id)
        assert_can_view(self.ctx, claim)
        self.ctx.require_permission(PERM_DOC_DOWNLOAD)
        document = await self.children.document(document_id)
        if document is None or document.claim_id != claim.id:
            raise ResourceNotFoundError()
        if document.kind == "MEDICAL" and not self.ctx.allows("claim:view_sensitive"):
            raise AuthorizationError("Medical documents require sensitive-information access")
        payload = await asyncio.to_thread(read_claim_document, document.storage_path)
        self.session.add(
            ClaimDocumentAccess(
                tenant_id=self.ctx.tenant_id,
                document_id=document.id,
                claim_id=claim.id,
                user_id=self.ctx.user_id,
                access_kind="DOWNLOAD",
                ip_address=ip_address,
                user_agent=(user_agent or "")[:512] or None,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="DOCUMENT_DOWNLOADED",
            summary=document.original_filename,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return document, payload

    async def delete_document(self, claim_id: UUID, document_id: UUID) -> Claim:
        claim = await self.repo.get(claim_id)
        assert_can_act(self.ctx, claim, PERM_DOC_DELETE)
        document = await self.children.document(document_id)
        if document is None or document.claim_id != claim.id:
            raise ResourceNotFoundError()
        document.deleted_at = _now()
        document.deleted_by_user_id = self.ctx.user_id
        await self.events.record(
            claim_id=claim.id,
            action="DOCUMENT_UPLOADED",
            summary=f"Removed document {document.original_filename}",
        )
        return claim

    async def remember_webhook(
        self,
        *,
        provider: str,
        nonce: str,
        timestamp_header: str | None,
        payload_hash: str,
        external_reference: str | None,
        claim_id: UUID | None,
        result: str,
        detail: str | None = None,
    ) -> ClaimWebhookReceipt | None:
        existing = await self.session.scalar(
            select(ClaimWebhookReceipt).where(
                ClaimWebhookReceipt.provider == provider,
                ClaimWebhookReceipt.nonce == nonce,
            )
        )
        if existing is not None:
            return existing
        receipt = ClaimWebhookReceipt(
            tenant_id=self.ctx.tenant_id if self.ctx.role_code != "webhook" else None,
            provider=provider,
            nonce=nonce,
            timestamp_header=timestamp_header,
            payload_hash=payload_hash,
            external_reference=external_reference,
            claim_id=claim_id,
            result=result,
            detail=detail,
        )
        self.session.add(receipt)
        await self.session.flush()
        return None

    async def _detail(self, claim: Claim) -> dict[str, Any]:
        include_payments = self.ctx.allows(PERM_PAY_READ)
        extras = await self.children.load_detail_collections(
            claim.id,
            include_internal_notes=self.ctx.allows(PERM_NOTE_READ),
            include_payments=include_payments,
        )
        approvals = extras.get("approvals") or []
        already_approved = any(
            not row.get("superseded")
            and row.get("decision") == "APPROVED"
            and row.get("approver_user_id") == str(self.ctx.user_id)
            for row in approvals
            if isinstance(row, dict)
        )
        for row in approvals:
            if isinstance(row, dict):
                row.pop("approver_user_id", None)
        if not include_payments:
            extras.pop("payments", None)
        extras["capabilities"] = compute_capabilities(
            self.ctx, claim, already_approved=already_approved
        ).model_dump()
        return await to_detail(
            self.session,
            self.ctx,
            claim,
            extras=extras,
            already_approved=already_approved,
        )

    async def _locked(self, claim_id: UUID) -> Claim:
        claim = await self.repo.get_for_update(claim_id)
        assert_can_view(self.ctx, claim)
        return claim

    async def _transition(self, claim: Claim, target: str, *, system: bool = False) -> None:
        assert_transition(claim.status, target, system=system)
        claim.status = target
        self._bump(claim)

    def _bump(self, claim: Claim) -> None:
        claim.version = int(claim.version) + 1

    def _set_payee(self, claim: Claim, beneficiary_type: str) -> None:
        if beneficiary_type not in {item.value for item in BeneficiaryType}:
            raise ValidationAppError("Payee must be the policyholder or the agency")
        claim.beneficiary_type = beneficiary_type

    async def _assign(
        self,
        claim: Claim,
        *,
        assigned_to: UUID,
        reason: str,
        note: str | None,
        is_new: bool = False,
    ) -> None:
        if not is_new:
            for row in await self.children.open_assignments(claim.id):
                row.ended_at = _now()
        claim.assigned_to_user_id = assigned_to
        self.session.add(
            ClaimAssignment(
                tenant_id=self.ctx.tenant_id,
                claim_id=claim.id,
                assigned_to_user_id=assigned_to,
                assigned_by_user_id=self.ctx.actor_user_id,
                assigned_at=_now(),
                reason=reason,
                note=note,
            )
        )

    async def _attach_handoff_task(
        self,
        claim: Claim,
        task: ClaimHandoffTask | None,
        *,
        assigned_to: UUID | None,
    ) -> None:
        if task is None:
            return
        subject = task.subject.strip()
        message = task.message.strip()
        if not subject or not message:
            raise ValidationAppError("Add a task title and a short note")
        followup_type = (
            task.followup_type
            if task.followup_type in {item.value for item in FollowupType}
            else FollowupType.INTERNAL_REVIEW.value
        )
        self.session.add(
            ClaimFollowup(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                followup_type=followup_type,
                subject=subject,
                message=message,
                status=FollowupStatus.OPEN.value,
                created_by_user_id=self.ctx.user_id,
                assigned_to_user_id=assigned_to or claim.assigned_to_user_id,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="FOLLOWUP_CREATED",
            summary=subject,
            metadata={"type": followup_type, "handoff": True},
        )
