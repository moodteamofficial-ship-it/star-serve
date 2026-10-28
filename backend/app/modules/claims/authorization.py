"""Claim access, segregation of duties, and approval-limit evaluation.

The UI never participates. Every check uses the live principal + database policy.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.claims.enums import (
    CORE_FACT_LOCK_STATUSES,
    FINANCIAL_LOCK_STATUSES,
    TERMINAL_STATUSES,
    ClaimStatus,
    Duty,
)
from app.modules.claims.models import (
    ApprovalPolicy,
    Claim,
    ClaimApproval,
    ClaimDutyAction,
    SegregationPolicy,
)

PERM_READ = "claim:read"
PERM_CREATE = "claim:create"
PERM_UPDATE = "claim:update"
PERM_ASSIGN = "claim:assign"
PERM_VET = "claim:vet"
PERM_REQUEST_INFO = "claim:request_information"
PERM_RECOMMEND = "claim:recommend_approval"
PERM_APPROVE = "claim:approve"
PERM_REJECT = "claim:reject"
PERM_FORWARD = "claim:forward"
PERM_VIEW_SENSITIVE = "claim:view_sensitive"
PERM_DOC_UPLOAD = "claim:document:upload"
PERM_DOC_DELETE = "claim:document:delete"
PERM_DOC_DOWNLOAD = "claim:document:download"
PERM_NOTE_READ = "claim:note:read"
PERM_NOTE_CREATE = "claim:note:create"
PERM_CLIENT_MESSAGE = "claim:client:message"
PERM_FOLLOWUP_CREATE = "claim:followup:create"
PERM_FOLLOWUP_COMPLETE = "claim:followup:complete"
PERM_PAY_AUTH = "claim:payment:authorize"
PERM_PAY_EXEC = "claim:payment:execute"
PERM_PAY_READ = "claim:payment:read"
PERM_PAY_RETRY = "claim:payment:retry"
PERM_CLOSE = "claim:close"
PERM_SUPERVISE = "claim:supervise"
PERM_OVERRIDE_WORKFLOW = "claim:override_workflow"
PERM_OVERRIDE_ASSIGNMENT = "claim:override_assignment"
PERM_OVERRIDE_LIMIT = "claim:override_approval_limit"
PERM_OVERRIDE_SOD = "claim:override_sod"

# Actions that require the caller to be assigned (unless supervise/override).
ASSIGNMENT_REQUIRED_PERMISSIONS = frozenset(
    {
        PERM_UPDATE,
        PERM_VET,
        PERM_REQUEST_INFO,
        PERM_RECOMMEND,
        PERM_APPROVE,
        PERM_REJECT,
        PERM_FORWARD,
        PERM_DOC_UPLOAD,
        PERM_DOC_DELETE,
        PERM_NOTE_CREATE,
        PERM_CLIENT_MESSAGE,
        PERM_FOLLOWUP_CREATE,
        PERM_FOLLOWUP_COMPLETE,
        PERM_CLOSE,
    }
)

DEFAULT_DUTY_CONFLICTS: tuple[tuple[str, str], ...] = (
    (Duty.VET.value, Duty.APPROVE.value),
    (Duty.VET.value, Duty.AUTHORIZE_PAYMENT.value),
    (Duty.VET.value, Duty.EXECUTE_PAYMENT.value),
    (Duty.APPROVE.value, Duty.AUTHORIZE_PAYMENT.value),
    (Duty.APPROVE.value, Duty.EXECUTE_PAYMENT.value),
    (Duty.AUTHORIZE_PAYMENT.value, Duty.EXECUTE_PAYMENT.value),
    (Duty.VET.value, Duty.MARK_PAYMENT_SUCCESS.value),
    (Duty.APPROVE.value, Duty.MARK_PAYMENT_SUCCESS.value),
    (Duty.AUTHORIZE_PAYMENT.value, Duty.MARK_PAYMENT_SUCCESS.value),
    (Duty.EXECUTE_PAYMENT.value, Duty.MARK_PAYMENT_SUCCESS.value),
)

MANDATORY_VETTING_KEYS = (
    "claimant_verified",
    "policy_active_at_incident",
    "coverage_confirmed",
    "documents_complete",
    "accident_details_consistent",
    "no_unresolved_followups",
)


def _allows(ctx: SecurityContext, permission: str) -> bool:
    return ctx.allows(permission)


def can_supervise(ctx: SecurityContext) -> bool:
    return ctx.is_platform_admin or _allows(ctx, PERM_SUPERVISE)


def is_assignee(ctx: SecurityContext, claim: Claim) -> bool:
    return claim.assigned_to_user_id is not None and claim.assigned_to_user_id == ctx.user_id


def is_creator(ctx: SecurityContext, claim: Claim) -> bool:
    return claim.created_by_user_id is not None and claim.created_by_user_id == ctx.user_id


def assert_tenant_and_branch(ctx: SecurityContext, claim: Claim) -> None:
    ctx.require_staff_principal()
    ctx.require_active_tenant()
    ctx.assert_same_tenant(claim.tenant_id)
    ctx.assert_branch_access(claim.branch_id)


def assert_can_view(ctx: SecurityContext, claim: Claim) -> None:
    ctx.require_permission(PERM_READ)
    assert_tenant_and_branch(ctx, claim)
    if (
        ctx.is_platform_admin
        or can_supervise(ctx)
        or is_assignee(ctx, claim)
        or is_creator(ctx, claim)
    ):
        return
    raise AuthorizationError("You are not assigned to this claim")


def assert_can_act(
    ctx: SecurityContext,
    claim: Claim,
    permission: str,
    *,
    require_assignment: bool | None = None,
) -> None:
    ctx.require_permission(permission)
    assert_tenant_and_branch(ctx, claim)
    needs_assignment = (
        require_assignment
        if require_assignment is not None
        else permission in ASSIGNMENT_REQUIRED_PERMISSIONS
    )
    if not needs_assignment:
        return
    if is_assignee(ctx, claim) or can_supervise(ctx):
        return
    if permission == PERM_UPDATE and is_creator(ctx, claim) and claim.status == ClaimStatus.CLAIM_DRAFT.value:
        return
    if _allows(ctx, PERM_OVERRIDE_ASSIGNMENT):
        return
    raise AuthorizationError("You must be assigned to this claim to perform that action")


def assert_not_terminal(claim: Claim) -> None:
    if claim.status in TERMINAL_STATUSES:
        raise ConflictError("This claim is closed to further workflow changes")


def assert_version(claim: Claim, expected: int | None) -> None:
    if expected is None:
        raise ValidationAppError("Claim version is required")
    if claim.version != expected:
        raise ConflictError("This claim was updated by someone else. Reload and try again.")


def editable_fields(claim: Claim) -> set[str]:
    if claim.status in TERMINAL_STATUSES:
        return set()
    if claim.status == ClaimStatus.CLAIM_DRAFT.value:
        return {
            "incident_date",
            "incident_time",
            "incident_location",
            "incident_description",
            "police_abstract_number",
            "vehicle_registration",
            "vehicle_make",
            "vehicle_model",
            "chassis_number",
            "driver_name",
            "driver_license_number",
            "damage_description",
            "injury_summary",
            "claimed_amount",
            "beneficiary_type",
            "beneficiary_reference",
        }
    if claim.status in {
        ClaimStatus.CLAIM_SUBMITTED.value,
        ClaimStatus.VETTING.value,
        ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
    }:
        return {
            "incident_location",
            "incident_description",
            "police_abstract_number",
            "damage_description",
            "injury_summary",
            "driver_name",
            "driver_license_number",
        }
    return set()


def assert_fields_editable(claim: Claim, fields: set[str]) -> None:
    allowed = editable_fields(claim)
    locked = fields - allowed
    if locked:
        raise ConflictError(
            "These fields are locked in the current claim state: " + ", ".join(sorted(locked))
        )
    if "claimed_amount" in fields and claim.status in FINANCIAL_LOCK_STATUSES:
        raise ConflictError("Approved financial information cannot be changed directly")
    if fields & {
        "incident_date",
        "vehicle_registration",
        "chassis_number",
    } and claim.status in CORE_FACT_LOCK_STATUSES:
        raise ConflictError("Core accident facts are locked after vetting")


def validate_vetting_checklist(checklist: dict[str, object], *, decision: str) -> None:
    if decision != "PASS":
        return
    missing = [key for key in MANDATORY_VETTING_KEYS if not bool(checklist.get(key))]
    if missing:
        raise ValidationAppError(
            "Vetting cannot pass until all mandatory checks are complete: " + ", ".join(missing)
        )


async def record_duty(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    claim_id: UUID,
    duty: str,
    user_id: UUID,
) -> None:
    existing = await session.scalar(
        select(ClaimDutyAction).where(
            ClaimDutyAction.claim_id == claim_id,
            ClaimDutyAction.duty == duty,
            ClaimDutyAction.user_id == user_id,
        )
    )
    if existing is not None:
        return
    session.add(
        ClaimDutyAction(tenant_id=tenant_id, claim_id=claim_id, duty=duty, user_id=user_id)
    )


async def assert_segregation(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    claim_id: UUID,
    duty: str,
) -> None:
    if _allows(ctx, PERM_OVERRIDE_SOD):
        return
    prior = list(
        (
            await session.scalars(
                select(ClaimDutyAction).where(
                    ClaimDutyAction.claim_id == claim_id,
                    ClaimDutyAction.user_id == ctx.user_id,
                )
            )
        ).all()
    )
    prior_duties = {row.duty for row in prior}
    policies = list(
        (
            await session.scalars(
                select(SegregationPolicy).where(
                    SegregationPolicy.tenant_id == ctx.tenant_id,
                    SegregationPolicy.active.is_(True),
                )
            )
        ).all()
    )
    conflicts = {(p.left_duty, p.right_duty): p.allowed for p in policies}
    for left, right in DEFAULT_DUTY_CONFLICTS:
        allowed = conflicts.get((left, right), conflicts.get((right, left), False))
        if allowed:
            continue
        if duty == right and left in prior_duties:
            raise AuthorizationError(
                f"Segregation of duties: you already performed {left} on this claim"
            )
        if duty == left and right in prior_duties:
            raise AuthorizationError(
                f"Segregation of duties: you already performed {right} on this claim"
            )


async def resolve_approval_policy(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    amount: Decimal,
    claim_type: str,
) -> ApprovalPolicy | None:
    stmt = (
        select(ApprovalPolicy)
        .where(
            ApprovalPolicy.tenant_id == ctx.tenant_id,
            ApprovalPolicy.role_id == ctx.role_id,
            ApprovalPolicy.active.is_(True),
            ApprovalPolicy.claim_type == claim_type,
            ApprovalPolicy.minimum_amount <= amount,
            ApprovalPolicy.maximum_amount >= amount,
        )
        .order_by(ApprovalPolicy.maximum_amount.asc())
    )
    return await session.scalar(stmt)


async def assert_approval_authority(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    claim: Claim,
    amount: Decimal,
) -> ApprovalPolicy:
    policy = await resolve_approval_policy(
        session, ctx, amount=amount, claim_type=claim.claim_type
    )
    if policy is None and not _allows(ctx, PERM_OVERRIDE_LIMIT):
        raise AuthorizationError("This amount is outside your approval authority")
    if policy is None:
        # Explicit override permission — still audited by the caller.
        policy = ApprovalPolicy(
            tenant_id=ctx.tenant_id,
            role_id=ctx.role_id,
            minimum_amount=Decimal("0"),
            maximum_amount=amount,
            claim_type=claim.claim_type,
            requires_second_approval=True,
            active=True,
        )
    return policy


async def active_approvals(
    session: AsyncSession, *, claim_id: UUID
) -> list[ClaimApproval]:
    rows = (
        await session.scalars(
            select(ClaimApproval)
            .where(
                ClaimApproval.claim_id == claim_id,
                ClaimApproval.superseded.is_(False),
                ClaimApproval.decision == "APPROVED",
            )
            .order_by(ClaimApproval.sequence.asc())
        )
    ).all()
    return list(rows)


async def assert_dual_approval_ready(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    claim: Claim,
    policy: ApprovalPolicy,
    amount: Decimal,
) -> bool:
    """Return True when this approval completes the required chain."""
    existing = await active_approvals(session, claim_id=claim.id)
    if any(row.approver_user_id == ctx.user_id for row in existing):
        raise AuthorizationError("A second distinct approver is required")
    needs_second = bool(policy.requires_second_approval)
    if policy.second_approval_above is not None and amount > policy.second_approval_above:
        needs_second = True
    if not needs_second:
        return True
    return len(existing) >= 1
