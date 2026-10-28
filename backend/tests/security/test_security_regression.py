"""Security regression contract for the remediation program.

These tests lock the invariants from the original acceptance criteria so a
later change cannot reopen a closed class of bug. They exercise the shared
primitives, not a single endpoint.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    TenantAccessError,
    ValidationAppError,
)
from app.core.security.branch_scope import BranchScope, resolve_branch_scope
from app.core.security.context import SecurityContext
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.core.security.media_url import sanitize_avatar_url
from app.core.security.permissions import effective_permissions
from app.integrations.payments.ports import WebhookVerificationResult
from app.main import _assert_production_secrets
from app.modules.certificates.service import to_public as cert_to_public
from app.modules.customers.enums import CustomerOrigin
from app.modules.customers.service import CustomerService
from app.modules.guest.insurance_gateway import GuestInsuranceGateway
from app.modules.guest.ownership import (
    GUEST_RESOURCE_ERROR,
    require_owned_customer,
    require_owned_customer_ctx,
    require_owned_policy_ctx,
)
from app.modules.guest.service import GuestService
from app.modules.insurance.issuance_schemas import IssuancePayRequest
from app.modules.insurance.issuance_service import IssuanceService
from app.modules.payments.enums import PaymentMethod
from app.modules.payments.schemas import PaymentInitiateRequest
from app.modules.payments.service import PaymentService, TERMINAL_STATUSES
from app.modules.payments.webhook_bind import (
    IDENTITY_REFERENCE,
    assert_webhook_bound_to_payment,
    authenticated_payment_lookup,
    may_apply_failure,
)
from app.modules.roles import router as roles_router
from app.modules.wallets.service import WalletService


def _guest(**overrides) -> GuestContext:
    values = {
        "session_id": uuid4(),
        "tenant_id": uuid4(),
        "tenant_status": "ACTIVE",
        "app_env": "test",
    }
    values.update(overrides)
    return GuestContext(**values)


def _staff(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "agent@agency.local",
        "role_id": uuid4(),
        "role_code": "agent",
        "permissions": {"customer:read"},
    }
    values.update(overrides)
    return SecurityContext(**values)


# --- Guest plane ---


def test_guest_cannot_use_staff_permissions_or_services() -> None:
    ctx = _guest().as_execution_context()
    with pytest.raises(AuthorizationError):
        ctx.require_staff_principal()
    with pytest.raises(AuthorizationError):
        ctx.require_permission("customer:read")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("payment:reconcile")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("wallet:read")


@pytest.mark.asyncio
async def test_guest_cannot_list_customers_payments_or_wallet() -> None:
    ctx = _guest().as_execution_context()
    with pytest.raises(AuthorizationError):
        await CustomerService(None, ctx).list(page=1, limit=10, query=None)  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await CustomerService(None, ctx).get(uuid4())  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await CustomerService(None, ctx).update(uuid4(), SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await PaymentService(None, ctx, None).list(  # type: ignore[arg-type]
            page=1, limit=10, query=None, status=None
        )
    with pytest.raises(AuthorizationError):
        await PaymentService(None, ctx, None).confirm_receipt(  # type: ignore[arg-type]
            uuid4(), receipt="ABC1234567"
        )
    with pytest.raises(AuthorizationError):
        await WalletService(None, ctx).list_transactions(page=1, limit=10)  # type: ignore[arg-type]


def test_guest_cannot_impersonate_staff_or_other_guest_customer() -> None:
    owner = _guest()
    attacker = _guest()
    staff_row = SimpleNamespace(origin=CustomerOrigin.STAFF.value, guest_session_id=None)
    other = SimpleNamespace(
        origin=CustomerOrigin.GUEST.value, guest_session_id=owner.session_id
    )
    with pytest.raises(AuthorizationError, match="cannot use this resource"):
        require_owned_customer(staff_row, attacker)
    with pytest.raises(AuthorizationError):
        require_owned_customer(other, attacker)
    with pytest.raises(AuthorizationError):
        require_owned_customer_ctx(attacker.as_execution_context(), staff_row)


def test_guest_cannot_use_another_guest_policy() -> None:
    owner = _guest()
    attacker = _guest()
    customer_id = uuid4()
    customer = SimpleNamespace(
        id=customer_id,
        origin=CustomerOrigin.GUEST.value,
        guest_session_id=owner.session_id,
    )
    policy = SimpleNamespace(customer_id=customer_id)
    require_owned_policy_ctx(owner.as_execution_context(), policy, customer)
    with pytest.raises(AuthorizationError):
        require_owned_policy_ctx(attacker.as_execution_context(), policy, customer)
    with pytest.raises(AuthorizationError):
        require_owned_policy_ctx(
            owner.as_execution_context(),
            SimpleNamespace(customer_id=uuid4()),
            customer,
        )


@pytest.mark.asyncio
async def test_guest_cannot_invoke_privileged_definite_operations() -> None:
    gateway = GuestInsuranceGateway(SimpleNamespace())  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await gateway.check_wallet_balance(agent_code="A1")
    with pytest.raises(AuthorizationError):
        await gateway.check_intermediary(identification="IRA-1")
    with pytest.raises(AuthorizationError):
        await gateway.cancel_policy({})
    with pytest.raises(AuthorizationError):
        await gateway.get_policy_details({})
    with pytest.raises(AuthorizationError):
        await gateway.get_cancellation_reasons()
    with pytest.raises(AuthorizationError):
        await gateway.initiate_provider_payment({"PaymentMethod": 0})
    with pytest.raises(AuthorizationError):
        await gateway.initiate_provider_payment({"PaymentMethod": 4})
    wrap = inspect.getsource(GuestService.__init__)
    assert "GuestInsuranceGateway" in wrap


def test_guest_http_surface_cannot_reach_staff_routes() -> None:
    from app.modules.certificates import router as certs
    from app.modules.guest import router as guest
    from app.modules.insurance import router as insurance
    from app.modules.payments import router as payments

    guest_src = inspect.getsource(guest)
    assert "require_guest" in guest_src
    assert "require_permissions" not in guest_src
    assert "require_staff_or_guest" not in inspect.getsource(insurance)
    assert "require_staff_or_guest" not in inspect.getsource(payments)
    assert "require_staff_or_guest" not in inspect.getsource(certs)
    pay_src = inspect.getsource(GuestService.get_payment)
    cert_src = inspect.getsource(GuestService.download_certificate)
    assert "_require_owned_policy" in pay_src
    assert "GUEST_RESOURCE_ERROR" in pay_src
    assert "_require_owned_policy" in cert_src
    assert GUEST_RESOURCE_ERROR


def test_guest_tenants_expose_only_picker_fields() -> None:
    from app.modules.insurance.guest_session import list_guest_tenants

    source = inspect.getsource(list_guest_tenants)
    assert '"id"' in source
    assert '"name"' in source
    assert '"tenant_type"' in source
    assert "email" not in source
    assert "kra_pin" not in source
    assert "database" not in source.lower()


# --- Staff / session / branch ---


def test_staff_cannot_access_another_tenant() -> None:
    ctx = _staff()
    with pytest.raises(TenantAccessError):
        ctx.assert_same_tenant(uuid4())
    ctx.assert_same_tenant(ctx.tenant_id)
    admin = _staff(is_platform_admin=True)
    admin.assert_same_tenant(uuid4())


def test_empty_branch_assignments_are_zero_access() -> None:
    scope, ids = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"customer:read", "user:manage"},
        assigned_branch_ids=set(),
    )
    assert scope is BranchScope.NONE
    assert ids == set()


def test_locked_and_logout_revoke_are_server_side() -> None:
    from app.core.dependencies.auth import get_current_context
    from app.modules.auth import router as auth_router
    from app.modules.auth.service import AuthService

    access = inspect.getsource(get_current_context)
    auth = inspect.getsource(AuthService.authenticate)
    refresh = inspect.getsource(AuthService.refresh)
    logout = inspect.getsource(auth_router.logout)
    service_logout = inspect.getsource(AuthService.logout)
    assert "UserStatus.LOCKED.value" in access
    assert "revoked" in access
    assert "sess_status" in access
    assert "revoke_all_sessions" in auth
    assert "UserStatus.LOCKED.value" in refresh
    assert "revoke_all_sessions" in refresh
    assert logout.index("service.logout") < logout.index("_clear_auth_cookies")
    assert "verify_exp=False" in service_logout


def test_certificate_public_json_has_no_remote_locator() -> None:
    public = cert_to_public(
        SimpleNamespace(
            id=uuid4(),
            policy_id=uuid4(),
            payment_id=None,
            customer_id=None,
            certificate_number="C1",
            status="GENERATED",
            external_certificate_ref=None,
            storage_key="https://blob.core.windows.net/x?sig=secret",
            provider_cert_url="https://uat.definiteassurance.com/c.pdf",
            local_file_path="tenant/c.pdf",
            local_stored_at=None,
            content_sha256=None,
            file_size_bytes=None,
            access_count=0,
            last_accessed_at=None,
            last_accessed_by_user_id=None,
            download_url_expires_at=None,
            generated_at=None,
            failure_message=None,
            job_id=None,
            created_at=None,
            updated_at=None,
        )
    )
    blob = str(public)
    assert "storage_key" not in public
    assert "provider_cert_url" not in public
    assert "https://" not in blob
    assert "sig=secret" not in blob


# --- Payments ---


def test_client_cannot_declare_payment_success_or_amount() -> None:
    with pytest.raises(ValidationError):
        IssuancePayRequest(policy_id=str(uuid4()), amount=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        PaymentInitiateRequest(  # type: ignore[call-arg]
            policy_id=uuid4(),
            method="BIRDVIEW",
            phone="254700000000",
            amount=1,
        )
    assert "SUCCESS" in TERMINAL_STATUSES


def test_forged_or_retargeted_birdview_callback_fails() -> None:
    payment = SimpleNamespace(
        reference="PAY-A",
        method=PaymentMethod.BIRDVIEW.value,
        provider_checkout_id="bv_stored",
    )
    forged_ref = WebhookVerificationResult(
        valid=True,
        reference="PAY-B",
        checkout_id="bv_stored",
        success=True,
        identity_kind=IDENTITY_REFERENCE,
    )
    kind, value = authenticated_payment_lookup(forged_ref)
    assert kind == IDENTITY_REFERENCE
    assert value == "PAY-B"
    with pytest.raises(AuthenticationError):
        assert_webhook_bound_to_payment(
            payment,  # type: ignore[arg-type]
            forged_ref,
            method=PaymentMethod.BIRDVIEW.value,
        )
    unsigned_fail = WebhookVerificationResult(
        valid=True,
        reference="PAY-A",
        checkout_id="bv_stored",
        success=False,
        outcome_authenticated=False,
        identity_kind=IDENTITY_REFERENCE,
    )
    assert may_apply_failure(unsigned_fail) is False
    apply_src = inspect.getsource(PaymentService.apply_webhook)
    assert "authenticated_payment_lookup" in apply_src
    assert "unsigned_failure_ignored" in apply_src
    assert "AMOUNT_MISMATCH" in apply_src
    assert "find_payment_by_checkout_global" not in apply_src.split("authenticated_payment_lookup")[0]
    assert apply_src.index("TERMINAL_STATUSES") < apply_src.index("PaymentStatus.SUCCESS")


def test_callback_ip_is_not_the_spoofable_xff_hop() -> None:
    from app.core.security import request as request_mod

    source = inspect.getsource(request_mod.proxy_observed_ip)
    assert "hops[-1]" in source
    assert 'split(",")[0]' not in source
    # Guest identity peels trusted platform hops; webhooks keep rightmost.
    identity = inspect.getsource(request_mod.end_user_ip)
    assert "trusted_proxy_hops" in identity
    assert "hops[-(peel + 1)]" in identity


def test_end_user_ip_peels_trusted_proxy_hops(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.core.security import request as request_mod

    monkeypatch.setattr(
        request_mod,
        "get_settings",
        lambda: SimpleNamespace(trust_x_forwarded_for=True, trusted_proxy_hops=2),
    )
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.9, 34.1.1.1, 35.2.2.2"},
        client=SimpleNamespace(host="10.0.0.8"),
    )
    assert request_mod.end_user_ip(request) == "203.0.113.9"
    assert request_mod.proxy_observed_ip(request) == "35.2.2.2"
    assert request_mod.client_ip(request) == "35.2.2.2"


def test_end_user_ip_ignores_leading_spoof_with_hop_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.core.security import request as request_mod

    monkeypatch.setattr(
        request_mod,
        "get_settings",
        lambda: SimpleNamespace(trust_x_forwarded_for=True, trusted_proxy_hops=1),
    )
    request = SimpleNamespace(
        headers={"x-forwarded-for": "1.1.1.1, 203.0.113.9, 34.8.8.8"},
        client=SimpleNamespace(host="10.0.0.8"),
    )
    # Peel 1 platform hop from the right → real client, not the spoofed lead.
    assert request_mod.end_user_ip(request) == "203.0.113.9"


# --- Admin / production ---


def test_tenant_admin_cannot_hold_or_grant_platform_wildcard() -> None:
    assert effective_permissions(
        is_platform_admin=False, permissions={"*:*", "role:manage"}
    ) == {"role:manage"}
    ctx = _staff(permissions={"*:*"})
    with pytest.raises(AuthorizationError):
        ctx.require_permission("platform:tenant:manage")
    grant = inspect.getsource(roles_router.replace_role_permissions)
    assert "is_platform_only_permission" in grant
    assert "PLATFORM_WILDCARD" in grant


def test_assigned_user_must_be_a_live_tenant_principal() -> None:
    assert "require_assignable_tenant_user" in inspect.getsource(CustomerService.assign)


def test_avatar_url_is_https_allowlisted() -> None:
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("javascript:alert(1)")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("https://127.0.0.1/a.png")


def test_production_cannot_silently_enable_financial_overrides() -> None:
    remote = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
        allow_insecure_production=True,
        allow_receipt_confirm=True,
        allow_manual_wallet_credit=True,
        csrf_secret="y" * 32,
        encryption_key="z" * 32,
        jwt_algorithm="RS256",
        guest_quote_enabled=False,
    )
    assert remote.receipt_confirm_allowed is False
    assert remote.manual_wallet_credit_allowed is False
    with pytest.raises(RuntimeError):
        _assert_production_secrets(remote)


def test_guest_capability_default_deny_is_closed() -> None:
    guest = _guest(capabilities=frozenset())
    with pytest.raises(AuthorizationError):
        guest.require(GuestCapability.CREATE_QUOTE)
    assert not any(":" in item.value for item in GuestCapability)


def test_issuance_shared_path_still_checks_guest_ownership() -> None:
    submit = inspect.getsource(IssuanceService.submit)
    assert "require_owned_customer_ctx" in submit
    assert "require_owned_customer_ctx" in inspect.getsource(IssuanceService._payable_policy)
    for method in (IssuanceService.pay, IssuanceService.cancel_pending_payment):
        assert "self._payable_policy(" in inspect.getsource(method)
