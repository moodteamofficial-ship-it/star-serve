"""Claims state machine, authority, and SoD — backend decides, UI does not."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AuthorizationError, ConflictError, ValidationAppError
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext
from app.modules.claims.authorization import (
    PERM_APPROVE,
    PERM_PAY_EXEC,
    PERM_UPDATE,
    PERM_VET,
    assert_can_act,
    assert_can_view,
    assert_fields_editable,
    validate_vetting_checklist,
)
from app.modules.claims.enums import ClaimStatus
from app.modules.claims.models import Claim
from app.modules.claims.capabilities import compute_capabilities
from app.modules.claims.schemas import (
    ClaimCreateRequest,
    ClaimInsurerDecisionRequest,
    ClaimSettlementRequest,
    ClaimUpdateRequest,
)
from app.modules.claims.workflow import SYSTEM_ONLY_TARGETS, assert_transition
from app.modules.roles.permissions_catalog import (
    CLAIM_OVERRIDE_PERMISSIONS,
    AGENCY_ADMIN_PERMISSIONS,
    PERMISSION_CATALOG,
    SYSTEM_ROLES,
)


def _ctx(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "officer@agency.local",
        "role_id": uuid4(),
        "role_code": "claims_officer",
        "permissions": {PERM_VET, "claim:read", PERM_UPDATE},
    }
    values.update(overrides)
    return SecurityContext(**values)


def _claim(**overrides) -> Claim:
    claim = Claim(
        tenant_id=uuid4(),
        customer_id=uuid4(),
        policy_id=uuid4(),
        claim_number="CLM-2026-TEST",
        status=ClaimStatus.VETTING.value,
        claimed_amount=Decimal("10000"),
        version=1,
    )
    for key, value in overrides.items():
        setattr(claim, key, value)
    return claim


def test_status_cannot_jump_to_definite_approved():
    with pytest.raises(ConflictError):
        assert_transition(ClaimStatus.VETTING.value, ClaimStatus.DEFINITE_APPROVED.value)


def test_staff_cannot_apply_system_only_status():
    pairs = [
        (ClaimStatus.SENT_TO_DEFINITE.value, ClaimStatus.DEFINITE_REVIEW.value),
        (ClaimStatus.DEFINITE_REVIEW.value, ClaimStatus.DEFINITE_APPROVED.value),
        (ClaimStatus.DEFINITE_REVIEW.value, ClaimStatus.DEFINITE_REJECTED.value),
        (ClaimStatus.PAYMENT_PROCESSING.value, ClaimStatus.PAYMENT_COMPLETED.value),
        (ClaimStatus.PAYMENT_PROCESSING.value, ClaimStatus.PAYMENT_FAILED.value),
    ]
    for current, target in pairs:
        assert target in SYSTEM_ONLY_TARGETS
        with pytest.raises(ConflictError):
            assert_transition(current, target, system=False)
        assert_transition(current, target, system=True)


def test_legal_vetting_pass_is_allowed():
    assert_transition(ClaimStatus.VETTING.value, ClaimStatus.VETTING_PASSED.value)


def test_create_schema_rejects_status_mass_assignment():
    with pytest.raises(ValidationError):
        ClaimCreateRequest(  # type: ignore[call-arg]
            policy_id=str(uuid4()),
            claimed_amount="1000",
            status="DEFINITE_APPROVED",
        )


def test_update_schema_rejects_status_and_approved_amount():
    with pytest.raises(ValidationError):
        ClaimUpdateRequest(version=1, status="CLOSED")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ClaimUpdateRequest(version=1, approved_amount="1")  # type: ignore[call-arg]


def test_vetting_pass_requires_mandatory_checklist():
    with pytest.raises(ValidationAppError):
        validate_vetting_checklist({"claimant_verified": True}, decision="PASS")
    validate_vetting_checklist(
        {
            "claimant_verified": True,
            "policy_active_at_incident": True,
            "coverage_confirmed": True,
            "documents_complete": True,
            "accident_details_consistent": True,
            "no_unresolved_followups": True,
        },
        decision="PASS",
    )


def test_platform_admin_can_view_guest_claim_from_another_agency():
    claim = _claim(channel="GUEST", assigned_to_user_id=None)
    ctx = _ctx(
        tenant_id=uuid4(),
        is_platform_admin=True,
        role_code="platform_admin",
        permissions={"*:*", "claim:read", "claim:supervise"},
        branch_scope=BranchScope.ALL_TENANT,
    )
    assert_can_view(ctx, claim)


def test_platform_admin_can_vet_unassigned_guest_claim_from_another_agency():
    claim = _claim(channel="GUEST", assigned_to_user_id=None)
    ctx = _ctx(
        tenant_id=uuid4(),
        is_platform_admin=True,
        role_code="platform_admin",
        permissions={"*:*", "claim:read", PERM_VET},
        branch_scope=BranchScope.ALL_TENANT,
    )
    assert_can_act(ctx, claim, PERM_VET)


def test_officer_cannot_approve_without_permission():
    ctx = _ctx()
    claim = _claim(tenant_id=ctx.tenant_id, assigned_to_user_id=ctx.user_id)
    with pytest.raises(AuthorizationError):
        assert_can_act(ctx, claim, PERM_APPROVE)


def test_unassigned_officer_cannot_vet():
    ctx = _ctx()
    claim = _claim(tenant_id=ctx.tenant_id, assigned_to_user_id=uuid4())
    with pytest.raises(AuthorizationError):
        assert_can_act(ctx, claim, PERM_VET)


def test_supervisor_can_act_without_assignment():
    ctx = _ctx(
        permissions={PERM_VET, "claim:read", "claim:supervise", "branch:all"},
        branch_scope=BranchScope.ALL_TENANT,
    )
    claim = _claim(tenant_id=ctx.tenant_id, assigned_to_user_id=uuid4())
    assert_can_act(ctx, claim, PERM_VET)


def test_locked_fields_after_vetting_passed():
    claim = _claim(status=ClaimStatus.VETTING_PASSED.value)
    with pytest.raises(ConflictError):
        assert_fields_editable(claim, {"incident_date"})
    with pytest.raises(ConflictError):
        assert_fields_editable(claim, {"claimed_amount"})


def test_agency_admin_does_not_auto_receive_overrides():
    assert CLAIM_OVERRIDE_PERMISSIONS.isdisjoint(AGENCY_ADMIN_PERMISSIONS)
    codes = {item["code"] for item in PERMISSION_CATALOG}
    assert "claim:vet" in codes
    assert "claim:payment:execute" in codes


def test_insurer_decision_schema_rejects_status_and_requires_decision():
    with pytest.raises(ValidationError):
        ClaimInsurerDecisionRequest(version=1, decision="MAYBE")  # type: ignore[call-arg]
    body = ClaimInsurerDecisionRequest(
        version=1,
        decision="APPROVED",
        approved_amount="100000",
        beneficiary_type="CLIENT",
    )
    assert body.decision == "APPROVED"
    settle = ClaimSettlementRequest(version=1, beneficiary_type="STAR_SERVE")
    assert settle.beneficiary_type == "STAR_SERVE"


def test_approver_cannot_see_approve_again_after_signing() -> None:
    ctx = _ctx(
        role_code="claims_manager",
        permissions={"claim:read", "claim:approve", "claim:supervise"},
    )
    claim = _claim(status=ClaimStatus.VETTING_PASSED.value, tenant_id=ctx.tenant_id)
    open_caps = compute_capabilities(ctx, claim)
    assert open_caps.can_approve is True
    assert open_caps.already_approved is False
    signed = compute_capabilities(ctx, claim, already_approved=True)
    assert signed.can_approve is False
    assert signed.already_approved is True


def test_manager_can_record_insurer_decision_while_file_is_with_them():
    ctx = _ctx(
        role_code="claims_manager",
        permissions={"claim:read", "claim:forward", "claim:supervise"},
    )
    claim = _claim(status=ClaimStatus.DEFINITE_REVIEW.value, tenant_id=ctx.tenant_id)
    caps = compute_capabilities(ctx, claim)
    assert caps.can_record_insurer_decision is True
    assert caps.can_record_settlement is False


def test_manager_can_record_settlement_after_insurer_approves():
    ctx = _ctx(
        role_code="claims_manager",
        permissions={"claim:read", "claim:forward", "claim:supervise"},
    )
    claim = _claim(status=ClaimStatus.PAYMENT_PENDING.value, tenant_id=ctx.tenant_id)
    caps = compute_capabilities(ctx, claim)
    assert caps.can_record_settlement is True
    assert caps.can_record_insurer_decision is False


def test_claim_reads_do_not_walk_child_tables_one_by_one() -> None:
    import inspect

    from app.modules.claims.repository import ClaimChildRepository, ClaimRepository
    from app.modules.claims.router import _written
    from app.modules.claims.service import ClaimService

    detail = inspect.getsource(ClaimService._detail)
    assert "load_detail_collections" in detail
    assert "await self.children.vettings" not in detail
    graph = inspect.getsource(ClaimChildRepository.load_detail_collections)
    assert "jsonb_agg" in graph
    assert "CAST(:cid AS uuid)" in graph
    assert "tenant_id = CAST(:tid AS uuid)" in graph
    counts = inspect.getsource(ClaimRepository.count_by_status)
    assert "func.count" in counts
    assert "group_by" in counts
    desk = inspect.getsource(ClaimRepository.desk_stats)
    assert "func.count().filter" in desk or "func.count()" in desk
    listed = inspect.getsource(ClaimRepository.search_listed)
    assert "func.count().over()" in listed
    search = inspect.getsource(ClaimRepository.search)
    assert "func.count" in inspect.getsource(ClaimRepository._scoped_count)
    assert "include_total" in search
    dashboard = inspect.getsource(ClaimService.dashboard)
    assert "desk_stats" in dashboard
    assert "queue_previews" not in dashboard
    written = inspect.getsource(_written)
    assert "service.present" in written
    assert "service.get" not in written


def test_assign_lists_staff_on_the_claim_tenant() -> None:
    import inspect

    from app.modules.claims.service import ClaimService

    source = inspect.getsource(ClaimService.list_assignees)
    assert "claim:assign" in source or "PERM_ASSIGN" in inspect.getsource(ClaimService)
    assert "User.tenant_id == claim.tenant_id" in source
    assert "claim:vet" in source


def test_assign_and_start_vetting_accept_an_optional_task() -> None:
    import inspect

    from app.modules.claims.schemas import ClaimAssignRequest, ClaimStartVettingRequest
    from app.modules.claims.service import ClaimService

    assignee = uuid4()
    assigned = ClaimAssignRequest(
        version=1,
        assigned_to_user_id=assignee,
        task={"subject": "Call the client", "message": "Need the police abstract"},
    )
    assert assigned.task is not None
    assert assigned.task.subject == "Call the client"
    started = ClaimStartVettingRequest(
        version=2,
        task={"subject": "Review photos", "message": "Check the damage shots"},
    )
    assert started.task is not None
    ClaimAssignRequest(version=1, assigned_to_user_id=assignee)
    ClaimStartVettingRequest(version=2)

    assign_src = inspect.getsource(ClaimService.assign)
    start_src = inspect.getsource(ClaimService.start_vetting)
    helper = inspect.getsource(ClaimService._attach_handoff_task)
    assert "_attach_handoff_task" in assign_src
    assert "_attach_handoff_task" in start_src
    assert "FOLLOWUP_CREATED" in helper


def test_claim_pdf_endpoint_is_a_read_of_the_live_file() -> None:
    import inspect

    from app.modules.claims import router, service

    source = inspect.getsource(router.download_claim_pdf)
    assert 'require_permissions("claim:read")' in source
    assert "application/pdf" in source
    assert inspect.getsource(service.ClaimService.download_pdf)
    assert "render_file_pdf" in inspect.getsource(service.ClaimService.download_pdf)
    assert "render_claim_pdf" in inspect.getsource(service.ClaimService.render_file_pdf)
    assert "generated_by" in inspect.getsource(service.ClaimService.render_file_pdf)
    assert "CLAIM_PDF_OPENED" in inspect.getsource(service.ClaimService.download_pdf)
    assert "CLAIM_PDF_DOWNLOADED" in inspect.getsource(service.ClaimService.download_pdf)
    assert "enqueue_downloaded_pdf_emails" in inspect.getsource(service.ClaimService.download_pdf)
    assert "persist_mail_pdf" in inspect.getsource(service.ClaimService.download_pdf)
    assert "await db.commit()" in source


def test_opening_a_claim_writes_who_viewed_it() -> None:
    import inspect

    from app.modules.claims import router, service

    route = inspect.getsource(router.record_claim_view)
    method = inspect.getsource(service.ClaimService.record_view)
    assert 'require_permissions("claim:read")' in route
    assert "CLAIM_OPENED" in method
    assert "latest_actor_action" in method
    assert "/view" in inspect.getsource(router)


def test_role_matrix_separates_vet_approve_and_pay():
    by_code = {spec["code"]: set(spec["permissions"]) for spec in SYSTEM_ROLES}  # type: ignore[arg-type]
    assert PERM_APPROVE not in by_code["claims_officer"]
    assert PERM_PAY_EXEC not in by_code["claims_officer"]
    assert PERM_PAY_EXEC not in by_code["finance_manager"]
    assert PERM_APPROVE not in by_code["payment_officer"]
    assert PERM_VET not in by_code["payment_officer"]
    assert PERM_APPROVE in by_code["claims_manager"]
    assert "claim:payment:authorize" in by_code["finance_manager"]
