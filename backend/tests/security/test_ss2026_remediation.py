"""Regression contract for SS-2026-01 through SS-2026-07."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, ValidationAppError
from app.core.security.branch_scope import (
    BranchScope,
    authorize_branch_access,
    resolve_branch_scope,
)
from app.core.security.context import SecurityContext
from app.core.security.filenames import content_disposition_header, sanitize_download_filename
from app.core.security.provider_config import (
    definite_integration_enabled,
    require_configured_definite_agent,
)
from app.main import _assert_production_secrets
from app.modules.insurance.issuance_service import (
    guest_submit_idempotency_key,
    resolve_proposal_client,
)
from app.modules.payments.service import to_public as payment_to_public
from app.modules.payments.webhook_bind import assert_policy_accepts_settlement
from app.modules.policies.enums import PolicyStatus


def _staff(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "agent@agency.local",
        "role_id": uuid4(),
        "role_code": "agent",
        "permissions": {"proposal:read"},
        "branch_scope": BranchScope.ASSIGNED,
        "branch_ids": {uuid4()},
    }
    values.update(overrides)
    return SecurityContext(**values)


# --- SS-2026-01 guest Definite OID ---


def test_guest_input_never_selects_definite_client_oid() -> None:
    stored_oid = "987654"
    guest_customer = SimpleNamespace(
        external_client_ref=stored_oid,
        id_number="12345678",
    )
    # Guest may only use the createClient OID stored on *their* customer row.
    assert resolve_proposal_client(is_guest=True, customer=guest_customer) == stored_oid
    guest_without_oid = SimpleNamespace(external_client_ref=None, id_number="12345678")
    assert resolve_proposal_client(is_guest=True, customer=guest_without_oid) is None
    staff_customer = SimpleNamespace(external_client_ref=stored_oid, id_number="12345678")
    assert resolve_proposal_client(is_guest=False, customer=staff_customer) == stored_oid
    staff_without_oid = SimpleNamespace(external_client_ref=None, id_number="12345678")
    assert resolve_proposal_client(is_guest=False, customer=staff_without_oid) == "12345678"


def test_issuance_submit_rejects_client_oid_field() -> None:
    from app.modules.insurance.issuance_schemas import IssuanceSubmitRequest

    assert "Client" not in IssuanceSubmitRequest.model_fields
    assert "ClientOID" not in IssuanceSubmitRequest.model_fields
    assert "PolicyHolder" not in IssuanceSubmitRequest.model_fields
    assert IssuanceSubmitRequest.model_config.get("extra") == "forbid"


def test_guest_ensure_client_binds_existing_definite_without_staff_attach() -> None:
    from app.modules.guest.service import GuestService

    source = inspect.getsource(GuestService.ensure_client)
    create = inspect.getsource(GuestService._create_guest_client)
    bind = inspect.getsource(GuestService._bind_session_guest_with_insurer_ref)
    assert "_returning_source" in source
    assert "_continue_returning_client" in source
    assert "_bind_session_guest_with_insurer_ref" in create
    assert "guest_client_insurer_bind" in create
    assert "_assert_guest_created_definite_identity" in create
    assert "GUEST_IDENTITY_ERROR" in create
    assert "created_ref" in create
    assert "CustomerOrigin.GUEST" in bind
    assert "find_by_id_number" not in source
    assert "find_by_id_number" not in create
    assert "find_by_id_number" not in bind


def test_guest_gateway_cannot_forward_client_oid() -> None:
    from app.modules.guest.insurance_gateway import GuestInsuranceGateway

    source = inspect.getsource(GuestInsuranceGateway.create_proposal)
    assert "_keep_numeric_oids" in source
    assert "require_configured_definite_agent" in source


def test_guest_submit_idempotency_is_session_scoped() -> None:
    session_a = uuid4()
    session_b = uuid4()
    customer = uuid4()
    key_a = guest_submit_idempotency_key(
        session_id=session_a,
        customer_id=customer,
        registration="KAA123A",
        product_code="COMP",
    )
    key_b = guest_submit_idempotency_key(
        session_id=session_b,
        customer_id=customer,
        registration="KAA123A",
        product_code="COMP",
    )
    assert key_a != key_b
    assert str(session_a) in key_a


def test_guest_submit_reuse_requires_same_pricing_terms() -> None:
    from app.modules.insurance.issuance_service import _quote_terms

    comp = _quote_terms(cover_option_id="3530", period="Monthly", capacity=1.0, sum_insured=0)
    tpo = _quote_terms(cover_option_id="3424", period="Monthly", capacity=1, sum_insured="0.00")
    assert comp != tpo
    assert tpo == _quote_terms(cover_option_id=3424, period="monthly", capacity="1", sum_insured=0)
    assert tpo != _quote_terms(cover_option_id="3424", period="Annually", capacity=1, sum_insured=0)
    assert tpo != _quote_terms(cover_option_id="3424", period="Monthly", capacity=2, sum_insured=0)

    session, customer = uuid4(), uuid4()
    base = {"session_id": session, "customer_id": customer, "registration": "KDSR888L", "product_code": "4653"}
    assert guest_submit_idempotency_key(**base, terms=":".join(comp)) != guest_submit_idempotency_key(
        **base, terms=":".join(tpo)
    )


# --- SS-2026-06 branch NULL isolation ---


def test_null_branch_is_not_authorized_for_assigned_agents() -> None:
    ctx = _staff()
    with pytest.raises(AuthorizationError):
        authorize_branch_access(ctx, None)
    with pytest.raises(AuthorizationError):
        authorize_branch_access(ctx, uuid4())
    authorize_branch_access(ctx, next(iter(ctx.branch_ids)))


def test_tenant_admin_keeps_explicit_cross_branch_access() -> None:
    ctx = _staff(branch_scope=BranchScope.ALL_TENANT, branch_ids=set())
    authorize_branch_access(ctx, None)
    authorize_branch_access(ctx, uuid4())


def test_empty_assignments_are_not_tenant_wide() -> None:
    scope, ids = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"proposal:read", "policy:read", "payment:read"},
        assigned_branch_ids=set(),
    )
    assert scope is BranchScope.NONE
    assert ids == set()
    with pytest.raises(AuthorizationError):
        authorize_branch_access(_staff(branch_scope=BranchScope.NONE, branch_ids=set()), uuid4())


def test_issuance_and_payments_stamp_trusted_branch() -> None:
    from app.modules.customers.service import CustomerService
    from app.modules.insurance.issuance_service import IssuanceService
    from app.modules.payments.service import PaymentService
    from app.modules.proposals.service import ProposalService

    customer_src = inspect.getsource(CustomerService.create)
    issue_src = inspect.getsource(IssuanceService.submit)
    pay_src = inspect.getsource(PaymentService.get_or_create_payment_attempt)
    proposal_src = inspect.getsource(ProposalService.create)
    assert "resolve_authorized_branch" in customer_src
    assert "resolve_authorized_branch" in issue_src
    assert "resolve_authorized_branch" in proposal_src
    assert "branch_id=branch_id" in proposal_src
    assert "branch_id" in issue_src
    assert "branch_id=getattr(policy" in pay_src or "branch_id=getattr(policy," in pay_src


# --- SS-2026-02 guest proposal bounds ---


def test_guest_submit_is_limited_and_idempotent() -> None:
    from app.modules.guest.service import GuestService
    from app.modules.insurance import guest_session
    from app.modules.insurance.issuance_service import IssuanceService

    guest_submit = inspect.getsource(GuestService.submit)
    issuance = inspect.getsource(IssuanceService.submit)
    assert "enforce_guest_submit_limit" in guest_submit
    assert "reserve_guest_submit_slot" in guest_submit
    assert "release_guest_submit_slot" in guest_submit
    assert "guest_submit_idempotency_key" in issuance
    assert "_reuse_guest_issuance" in issuance
    assert guest_session.GUEST_SUBMITS_PER_SESSION <= 3
    assert guest_session.GUEST_SUBMIT_ATTEMPTS_PER_SESSION <= 8


# --- SS-2026-07 single active STK ---


def test_policy_cannot_accept_a_second_settlement_once_active() -> None:
    policy = SimpleNamespace(
        tenant_id=uuid4(),
        status=PolicyStatus.ACTIVE.value,
    )
    with pytest.raises(Exception):
        assert_policy_accepts_settlement(policy, payment_tenant_id=policy.tenant_id)
    pending = SimpleNamespace(
        tenant_id=policy.tenant_id,
        status=PolicyStatus.PENDING_PAYMENT.value,
    )
    assert_policy_accepts_settlement(pending, payment_tenant_id=policy.tenant_id)


def test_payment_initiate_reuses_active_attempt() -> None:
    from app.modules.payments.enums import ACTIVE_PAYMENT_ATTEMPT_STATUSES, PaymentStatus
    from app.modules.payments.models import Payment
    from app.modules.payments.service import PaymentService

    assert PaymentStatus.PENDING.value in ACTIVE_PAYMENT_ATTEMPT_STATUSES
    assert PaymentStatus.SUCCESS.value not in ACTIVE_PAYMENT_ATTEMPT_STATUSES
    model_src = inspect.getsource(Payment)
    assert "uq_payments_one_active_per_policy" in model_src
    init_src = inspect.getsource(PaymentService.get_or_create_payment_attempt)
    assert "get_for_update" in init_src
    assert "find_active_attempt_for_policy" in init_src
    webhook = inspect.getsource(PaymentService.apply_webhook)
    assert "SUPERSEDED" in webhook
    assert "get_for_update" in webhook


# --- SS-2026-03 agent fallback ---


def test_hardcoded_definite_agent_fallback_is_impossible() -> None:
    from app.modules.insurance.issuance_service import IssuanceService

    source = inspect.getsource(IssuanceService.submit)
    assert "114181" not in source
    assert "require_configured_definite_agent" in source
    with pytest.raises(ValidationAppError, match="not configured"):
        require_configured_definite_agent(Settings(definite_assurance_agent_code=""))
    assert (
        require_configured_definite_agent(Settings(definite_assurance_agent_code=" 9911 "))
        == "9911"
    )


def test_production_requires_agent_when_definite_is_enabled() -> None:
    missing = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
        csrf_secret="y" * 32,
        encryption_key="z" * 32,
        jwt_algorithm="RS256",
        guest_quote_enabled=False,
        definite_assurance_username="da-user",
        definite_assurance_agent_code="",
    )
    assert definite_integration_enabled(missing) is True
    with pytest.raises(RuntimeError, match="DEFINITE_ASSURANCE_AGENT_CODE") as caught:
        _assert_production_secrets(missing)
    configured = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
        csrf_secret="y" * 32,
        encryption_key="z" * 32,
        jwt_algorithm="RS256",
        guest_quote_enabled=False,
        definite_assurance_username="da-user",
        definite_assurance_agent_code="991100",
        birdview_live=False,
    )
    _assert_production_secrets(configured)
    assert "991100" not in str(caught.value)
    assert require_configured_definite_agent.__doc__
    assert "991100" not in (require_configured_definite_agent.__doc__ or "")


# --- SS-2026-04 checkout id ---


def test_payment_public_omits_provider_checkout_id() -> None:
    public = payment_to_public(
        SimpleNamespace(
            id=uuid4(),
            customer_id=None,
            policy_id=None,
            proposal_id=None,
            reference="PAY-1",
            purpose="POLICY_PREMIUM",
            method="BIRDVIEW",
            currency="KES",
            amount="10.00",
            status="PENDING",
            phone="254700000000",
            provider="BIRDVIEW",
            provider_checkout_id="bv_secret_checkout",
            provider_receipt=None,
            failure_code=None,
            failure_message=None,
            paid_at=None,
            version=1,
            job_id=None,
            created_at=None,
            updated_at=None,
        )
    )
    assert "provider_checkout_id" not in public
    assert "bv_secret_checkout" not in str(public)


# --- SS-2026-05 filename ---


@pytest.mark.parametrize(
    ("raw", "must_not"),
    [
        ("../../evil.pdf", ["..", "/"]),
        ("file.pdf\r\nX-Injected: 1", ["\r", "\n", "X-Injected"]),
        ('quote"name.pdf', ['"']),
        ("", []),
        (None, []),
        ("<script>x.pdf", ["<", ">"]),
        ("a" * 400 + ".pdf", []),
    ],
)
def test_certificate_filename_is_sanitized(raw: str | None, must_not: list[str]) -> None:
    safe = sanitize_download_filename(raw)
    assert "\r" not in safe
    assert "\n" not in safe
    assert "/" not in safe
    assert "\\" not in safe
    assert '"' not in safe
    for token in must_not:
        assert token not in safe
    header = content_disposition_header("attachment", raw)
    assert "\r" not in header
    assert "\n" not in header
    assert header.startswith("attachment; filename=")


def test_normal_filename_is_preserved() -> None:
    assert sanitize_download_filename("CERT-ABC123.pdf") == "CERT-ABC123.pdf"


def test_unicode_filename_is_normalized() -> None:
    safe = sanitize_download_filename("证书.pdf")
    assert safe.endswith(".pdf")
    assert "\n" not in safe


# --- SS-2026-08 notification branch isolation ---


def test_outbound_requires_db_channel_flags() -> None:
    from app.modules.notifications.dispatcher import EmailDispatcher
    from app.modules.notifications.service import NotificationService
    from app.modules.system_config.service import SystemConfigService

    send_src = inspect.getsource(NotificationService.send)
    deliver_src = inspect.getsource(NotificationService.deliver)
    drain_src = inspect.getsource(EmailDispatcher._drain)
    one_src = inspect.getsource(EmailDispatcher._send_one)
    assert "require_outbound" in send_src
    assert "outbound_allowed" in deliver_src
    assert "outbound_allowed" in drain_src
    assert "outbound_allowed" in one_src
    assert "live=True" in inspect.getsource(SystemConfigService.require_outbound)
    allowed_src = inspect.getsource(SystemConfigService.outbound_allowed)
    assert "live: bool = True" in allowed_src
    assert "is_channel_enabled" in allowed_src


def test_notifications_are_branch_owned() -> None:
    from app.modules.notifications.models import Notification
    from app.modules.notifications.service import NotificationService

    assert getattr(Notification, "branch_id", None) is not None
    send_src = inspect.getsource(NotificationService.send)
    get_src = inspect.getsource(NotificationService.get)
    deliver_src = inspect.getsource(NotificationService.deliver)
    cancel_src = inspect.getsource(NotificationService.cancel)
    assert "resolve_authorized_branch" in send_src
    assert "branch_id=branch_id" in send_src
    assert "assert_branch_access" in get_src
    assert "assert_branch_access" in deliver_src
    assert "assert_branch_access" in cancel_src


def test_notification_list_count_uses_branch_scope() -> None:
    from app.modules.notifications.repository import NotificationRepository

    source = inspect.getsource(NotificationRepository.search)
    assert "_count_select" in source
    assert "Notification.tenant_id == self.ctx.tenant_id" not in source


# --- SS-2026-09 guest pay redaction ---


def test_guest_pay_redacts_provider_ids() -> None:
    from app.modules.guest.service import GuestService

    view_src = inspect.getsource(GuestService._guest_issuance_view)
    pay_src = inspect.getsource(GuestService.pay)
    assert "external_policy_ref" in view_src
    assert "provider_note_oid" in view_src
    assert "agent_code" in view_src
    assert "_guest_issuance_view" in pay_src
