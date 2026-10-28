"""Phase 2 — guest identity is not staff-customer ownership."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError
from app.core.security.guest_capabilities import GuestContext
from app.modules.customers.enums import CustomerOrigin
from app.modules.guest.ownership import (
    GUEST_IDENTITY_ERROR,
    GUEST_RESOURCE_ERROR,
    customer_owned_by_guest,
    require_owned_customer,
    require_owned_customer_ctx,
)
from app.core.security.context import SecurityContext


def _guest(**overrides) -> GuestContext:
    values = {
        "session_id": uuid4(),
        "tenant_id": uuid4(),
        "tenant_status": "ACTIVE",
        "app_env": "test",
    }
    values.update(overrides)
    return GuestContext(**values)


def test_id_and_phone_do_not_prove_ownership_of_staff_customer() -> None:
    guest = _guest()
    staff = SimpleNamespace(
        origin=CustomerOrigin.STAFF.value,
        guest_session_id=None,
        phone="+254700000000",
        id_number="12345678",
    )
    assert customer_owned_by_guest(staff, guest) is False
    with pytest.raises(AuthorizationError, match="cannot use this resource"):
        require_owned_customer(staff, guest)


def test_other_guest_session_cannot_claim_customer() -> None:
    owner = _guest()
    attacker = _guest()
    row = SimpleNamespace(
        origin=CustomerOrigin.GUEST.value,
        guest_session_id=owner.session_id,
    )
    assert customer_owned_by_guest(row, owner) is True
    assert customer_owned_by_guest(row, attacker) is False
    require_owned_customer(row, owner)
    with pytest.raises(AuthorizationError):
        require_owned_customer(row, attacker)


def test_guest_execution_adapter_cannot_use_staff_customer() -> None:
    guest = _guest()
    ctx = guest.as_execution_context()
    staff = SimpleNamespace(
        origin=CustomerOrigin.STAFF.value,
        guest_session_id=None,
    )
    with pytest.raises(AuthorizationError):
        require_owned_customer_ctx(ctx, staff)
    own = SimpleNamespace(
        origin=CustomerOrigin.GUEST.value,
        guest_session_id=guest.session_id,
    )
    require_owned_customer_ctx(ctx, own)
    staff_ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@example.com",
        role_id=uuid4(),
        role_code="agent",
        permissions={"customer:create"},
    )
    require_owned_customer_ctx(staff_ctx, staff)


def test_staff_ensure_client_rejects_guests_and_has_no_phone_reuse() -> None:
    from app.modules.insurance.service import InsuranceOrchestrationService

    source = inspect.getsource(InsuranceOrchestrationService.ensure_client)
    assert "require_staff_principal" in source
    assert "_assert_guest_may_reuse" not in source
    assert "is_guest" not in source
    assert not hasattr(InsuranceOrchestrationService, "_assert_guest_may_reuse")
    assert not hasattr(InsuranceOrchestrationService, "_guest_client_view")


def test_guest_ensure_client_never_looks_up_staff_customers() -> None:
    from app.modules.guest.service import GuestService

    source = inspect.getsource(GuestService.ensure_client)
    create = inspect.getsource(GuestService._create_guest_client)
    assert "find_guest_by_session_id_number" in source
    assert ".find_by_id_number(" not in source
    assert "_assert_guest_may_reuse" not in source
    assert "_returning_source" in source
    assert "_continue_returning_client" in source
    assert "_bind_session_guest_with_insurer_ref" in create
    assert "_assert_guest_created_definite_identity" in source
    assert "CustomerOrigin.GUEST" in create
    assert "IssuanceService" not in source
    assert "IssuanceService" not in create


def test_guest_returning_survives_unreadable_definite_when_agency_has_oid() -> None:
    """Passport checkClient can be unreadable; local returning + stored OID must proceed."""
    from app.modules.guest.service import GuestService

    continue_src = inspect.getsource(GuestService._continue_returning_client)
    lookup_src = inspect.getsource(GuestService._lookup_definite_client)
    assert_src = inspect.getsource(GuestService._assert_guest_created_definite_identity)
    returning_src = inspect.getsource(GuestService._returning_source)
    assert "source_ref" in continue_src
    assert "id_number_lookup_variants" in lookup_src
    assert "saw_clear_absent" in lookup_src
    assert "if stored:" in assert_src
    assert "preferred" in assert_src
    assert "id_number_compact" in returning_src
    assert 'func.replace(Customer.id_number, "-", "")' in returning_src


@pytest.mark.asyncio
async def test_guest_heals_missing_oid_so_same_client_can_quote_another_vehicle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Definite already has the person; session guest without OID should bind and continue."""
    from app.modules.guest.service import GuestService

    flushed = {"n": 0}

    class _Session:
        async def flush(self) -> None:
            flushed["n"] += 1

    svc = GuestService.__new__(GuestService)
    svc.session = _Session()

    async def _lookup(_idn: str):
        return {"external_ref": "554433"}

    monkeypatch.setattr(svc, "_lookup_definite_client", _lookup)
    customer = SimpleNamespace(id_number="12345678", external_client_ref=None)
    await svc._assert_guest_created_definite_identity(customer)
    assert customer.external_client_ref == "554433"
    assert flushed["n"] == 1

    # Already bound — no rewrite.
    flushed["n"] = 0
    await svc._assert_guest_created_definite_identity(customer)
    assert flushed["n"] == 0


@pytest.mark.asyncio
async def test_guest_keeps_real_oid_when_check_client_falls_back_to_id_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.guest.service import GuestService

    class _Session:
        async def flush(self) -> None:
            raise AssertionError("must not rewrite a real OID to the national ID")

    svc = GuestService.__new__(GuestService)
    svc.session = _Session()

    async def _lookup(_idn: str):
        return {"external_ref": "12345678"}

    monkeypatch.setattr(svc, "_lookup_definite_client", _lookup)
    customer = SimpleNamespace(id_number="12345678", external_client_ref="998877")
    await svc._assert_guest_created_definite_identity(customer)
    assert customer.external_client_ref == "998877"


def test_guest_identity_error_does_not_enumerate_accounts() -> None:
    assert "exist" not in GUEST_IDENTITY_ERROR.lower()
    assert "phone" not in GUEST_IDENTITY_ERROR.lower()
    assert "id number" not in GUEST_IDENTITY_ERROR.lower()
    assert "already" not in GUEST_IDENTITY_ERROR.lower()


def test_staff_id_lookup_excludes_guest_rows() -> None:
    from app.modules.customers.repository import CustomerRepository

    source = inspect.getsource(CustomerRepository.find_by_id_number)
    assert "CustomerOrigin.STAFF" in source
    guest_source = inspect.getsource(CustomerRepository.find_guest_by_session_id_number)
    assert "guest_session_id" in guest_source
    assert "CustomerOrigin.GUEST" in guest_source


def test_guest_resource_reads_hide_missing_as_forbidden() -> None:
    from app.modules.guest.service import GuestService

    get_pay = inspect.getsource(GuestService.get_payment)
    download = inspect.getsource(GuestService.download_certificate)
    submit = inspect.getsource(GuestService.submit)
    assert "ResourceNotFoundError" in get_pay
    assert "GUEST_RESOURCE_ERROR" in get_pay
    assert "ResourceNotFoundError" in download
    assert "_require_owned_policy" in get_pay
    assert "_require_owned_customer" in submit
    assert GUEST_RESOURCE_ERROR


def test_issuance_shared_path_enforces_guest_ownership() -> None:
    from app.modules.insurance.issuance_service import IssuanceService

    submit = inspect.getsource(IssuanceService.submit)
    assert "require_owned_customer_ctx" in submit
    assert "require_owned_customer_ctx" in inspect.getsource(IssuanceService._payable_policy)
    for method in (IssuanceService.pay, IssuanceService.cancel_pending_payment):
        assert "self._payable_policy(" in inspect.getsource(method)
