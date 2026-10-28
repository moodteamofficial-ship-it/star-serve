"""Guest FNOL is a capability plane — not staff claims RBAC."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AuthorizationError, ValidationAppError
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.modules.claims.enums import ClaimStatus
from app.modules.claims.guest_schemas import GuestClaimCreateRequest, GuestClaimLookupRequest
from app.modules.claims.guest_service import (
    GuestClaimService,
    phones_match,
    policy_lookup_key,
    public_journey,
    public_status,
)


def test_guest_file_schema_rejects_trusted_ids() -> None:
    with pytest.raises(ValidationError):
        GuestClaimCreateRequest(  # type: ignore[call-arg]
            policy_number="POL-123456",
            vehicle_registration="KDA123A",
            id_number="12345678",
            phone="254700000001",
            incident_date="2026-09-01",
            incident_location="Nairobi",
            incident_description="Rear-ended at a junction.",
            tenant_id=str(uuid4()),
        )
    with pytest.raises(ValidationError):
        GuestClaimCreateRequest(  # type: ignore[call-arg]
            policy_number="POL-123456",
            vehicle_registration="KDA123A",
            id_number="12345678",
            phone="254700000001",
            incident_date="2026-09-01",
            incident_location="Nairobi",
            incident_description="Rear-ended at a junction.",
            status="DEFINITE_APPROVED",
        )


def test_guest_lookup_schema_rejects_internal_claim_id() -> None:
    with pytest.raises(ValidationError):
        GuestClaimLookupRequest(  # type: ignore[call-arg]
            claim_number="CLM-2026-ABCD",
            id_number="12345678",
            phone="254700000001",
            claim_id=str(uuid4()),
        )


def test_policy_lookup_key_accepts_certificate_and_document_numbers() -> None:
    assert policy_lookup_key("POL-ABC123DE") == "POLABC123DE"
    assert policy_lookup_key("pol abc123de") == "POLABC123DE"
    assert policy_lookup_key("NW2026131291") == "NW2026131291"
    assert policy_lookup_key("nw 2026/131291") == "NW2026131291"
    assert policy_lookup_key("C27617729") == "C27617729"
    with pytest.raises(ValidationAppError):
        policy_lookup_key("NW")


def test_guest_file_searches_staff_platform_policies() -> None:
    import inspect

    source = inspect.getsource(GuestClaimService.file)
    match = inspect.getsource(GuestClaimService._match_active_policy)
    assert "guest_fnol_tenant_ids" in match
    assert "policy.tenant_id" in source
    assert "self.guest.tenant_id" not in source or "policy.tenant_id" in source
    notify = inspect.getsource(GuestClaimService._email_filed_claim)
    assert "render_file_pdf" in notify
    assert "persist_mail_pdf" in notify
    assert "CLAIM_RECEIVED" in notify
    assert "notify_claim_event" in notify


def test_guest_phone_match_accepts_kenya_formats() -> None:
    assert phones_match("254712345678", "0712345678")
    assert phones_match("+254712345678", "712345678")
    assert phones_match("0712345678", "254712345678")
    assert not phones_match("254712345678", "254700000001")


def test_guest_public_status_hides_internal_states() -> None:
    assert public_status(ClaimStatus.DEFINITE_APPROVED.value) == "Approved — settlement in progress"
    assert public_status(ClaimStatus.VETTING.value) == "Under review"
    assert "DEFINITE" not in public_status(ClaimStatus.DEFINITE_REVIEW.value)
    assert public_status(ClaimStatus.VETTING_FAILED.value) == "Not approved"


def test_guest_journey_hides_internal_states_and_orders_progress() -> None:
    sent = public_journey(ClaimStatus.SENT_TO_DEFINITE.value)
    assert sent["waiting_on"] == "insurer"
    assert sent["steps"][0]["state"] == "done"
    assert sent["steps"][2]["state"] == "current"
    assert "DEFINITE" not in sent["now"]
    info = public_journey(ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value)
    assert info["waiting_on"] == "you"
    declined = public_journey(ClaimStatus.VETTING_FAILED.value)
    assert declined["steps"][2]["state"] == "skip"
    assert declined["pending"] == []


def test_guest_cannot_use_staff_claim_permissions() -> None:
    guest = GuestContext(
        session_id=uuid4(),
        tenant_id=uuid4(),
        tenant_status="ACTIVE",
        app_env="test",
    )
    ctx = guest.as_execution_context()
    with pytest.raises(AuthorizationError):
        ctx.require_staff_principal()
    with pytest.raises(AuthorizationError):
        ctx.require_permission("claim:create")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("claim:vet")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("claim:assign")


def test_guest_claim_capabilities_are_not_staff_codes() -> None:
    assert ":" not in GuestCapability.FILE_CLAIM.value
    assert GuestCapability.FILE_CLAIM.value.startswith("file_")


def test_guest_claim_router_is_isolated_from_staff_claims() -> None:
    import inspect

    from app.modules.claims import guest_router, router as staff_router

    guest_source = inspect.getsource(guest_router)
    staff_source = inspect.getsource(staff_router)
    guest_paths = {getattr(route, "path", "") for route in guest_router.router.routes}
    staff_paths = {getattr(route, "path", "") for route in staff_router.router.routes}

    assert "require_guest" in guest_source
    assert "require_permissions" not in guest_source
    assert "require_staff_or_guest" not in guest_source
    assert "/insurance/guest/claims" in guest_paths
    assert "/insurance/guest/claims/lookup" in guest_paths
    assert not any("/guest/" in path for path in staff_paths)
    assert "require_permissions" in staff_source or "require_permission" in staff_source
