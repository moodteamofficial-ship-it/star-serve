"""Phase 1 — guest plane is not a lightweight staff principal."""

from __future__ import annotations

import inspect
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError
from app.core.security.branch_scope import BranchScope
from app.core.security.guest_capabilities import (
    GUEST_CAPABILITIES,
    GuestCapability,
    GuestContext,
)
from app.modules.customers.service import CustomerService
from app.modules.payments.service import PaymentService
from app.modules.wallets.service import WalletService


def _guest_context(**overrides) -> GuestContext:
    values = {
        "session_id": uuid4(),
        "tenant_id": uuid4(),
        "tenant_status": "ACTIVE",
        "app_env": "test",
    }
    values.update(overrides)
    return GuestContext(**values)


def _guest_execution():
    return _guest_context().as_execution_context()


def test_guest_capabilities_are_a_closed_allowlist() -> None:
    assert GUEST_CAPABILITIES == frozenset(GuestCapability)
    assert GuestCapability.CREATE_QUOTE in GUEST_CAPABILITIES
    assert GuestCapability.VIEW_QUOTE in GUEST_CAPABILITIES
    assert GuestCapability.INITIATE_PAYMENT in GUEST_CAPABILITIES
    assert GuestCapability.VIEW_PAYMENT in GUEST_CAPABILITIES
    assert GuestCapability.DOWNLOAD_CERTIFICATE in GUEST_CAPABILITIES
    assert GuestCapability.FILE_CLAIM in GUEST_CAPABILITIES
    assert GuestCapability.VIEW_OWN_CLAIM in GUEST_CAPABILITIES
    assert GuestCapability.FOLLOW_UP_CLAIM in GUEST_CAPABILITIES
    assert GuestCapability.APPLY_AS_AGENT in GUEST_CAPABILITIES
    # Staff catalog codes must never appear as guest capabilities.
    assert not any(":" in capability.value for capability in GuestCapability)


def test_guest_capability_default_deny() -> None:
    guest = _guest_context(capabilities=frozenset())
    with pytest.raises(AuthorizationError):
        guest.require(GuestCapability.CREATE_QUOTE)
    with pytest.raises(AuthorizationError):
        guest.require()


def test_guest_execution_adapter_cannot_satisfy_staff_auth() -> None:
    ctx = _guest_execution()
    assert ctx.is_guest is True
    assert ctx.permissions == set()
    assert ctx.branch_scope == BranchScope.ALL_TENANT
    assert ctx.actor_user_id is None
    with pytest.raises(AuthorizationError):
        ctx.require_staff_principal()
    with pytest.raises(AuthorizationError):
        ctx.require_permission("customer:create")
    with pytest.raises(AuthorizationError):
        ctx.require_any_permission("payment:read", "product:read")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("*:*")


async def test_staff_services_reject_guest_principal() -> None:
    ctx = _guest_execution()
    with pytest.raises(AuthorizationError):
        await CustomerService(None, ctx).get(uuid4())  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await PaymentService(None, ctx, None).list(page=1, limit=10, query=None, status=None)  # type: ignore[arg-type]
    with pytest.raises(AuthorizationError):
        await WalletService(None, ctx).list_transactions(page=1, limit=10)  # type: ignore[arg-type]


def test_require_guest_never_falls_back_to_staff() -> None:
    from app.modules.guest.deps import require_guest

    source = inspect.getsource(require_guest)
    assert "load_guest_context" in source
    assert "get_current_context" not in source
    assert "require_permissions" not in source


def test_guest_router_is_isolated_from_staff_permissions() -> None:
    from app.modules.guest import router as guest_router
    from app.modules.insurance import router as insurance_router

    guest_source = inspect.getsource(guest_router)
    staff_source = inspect.getsource(insurance_router)
    assert "require_guest" in guest_source
    assert "require_permissions" not in guest_source
    assert "require_staff_or_guest" not in guest_source
    assert "require_staff_or_guest" not in staff_source
    assert "load_guest_context" not in staff_source
    assert "require_permissions" in staff_source
    assert '/catalog"' in staff_source
    assert "/guest/catalog" in guest_source or '"/catalog"' in guest_source


def test_staff_payment_and_certificate_routes_do_not_accept_guests() -> None:
    from app.modules.certificates import router as certificates_router
    from app.modules.payments import router as payments_router

    payments_source = inspect.getsource(payments_router)
    certs_source = inspect.getsource(certificates_router)
    assert "require_staff_or_guest" not in payments_source
    assert "require_staff_or_guest" not in certs_source
    assert "is_guest" not in payments_source
    assert "assert_guest_owns_policy" not in certs_source


def test_guest_and_staff_http_surfaces_are_split() -> None:
    from app.modules.guest.router import router as guest_router
    from app.modules.insurance.router import router as staff_router
    from app.modules.payments.router import router as payments_router
    from app.modules.certificates.router import router as certificates_router

    guest_paths = {getattr(route, "path", "") for route in guest_router.routes}
    staff_paths = {getattr(route, "path", "") for route in staff_router.routes}
    payment_paths = {getattr(route, "path", "") for route in payments_router.routes}
    cert_paths = {getattr(route, "path", "") for route in certificates_router.routes}

    assert "/insurance/guest/tenants" in guest_paths
    assert "/insurance/guest/csrf" in guest_paths
    assert "/insurance/guest/session" in guest_paths
    assert "/insurance/guest/catalog" in guest_paths
    assert "/insurance/guest/premium" in guest_paths
    assert "/insurance/guest/client" in guest_paths
    assert "/insurance/guest/submit" in guest_paths
    assert "/insurance/guest/pay" in guest_paths
    assert "/insurance/guest/payments/{payment_id}" in guest_paths
    assert "/insurance/guest/certificates/{certificate_id}/download" in guest_paths
    assert "/insurance/catalog" in staff_paths
    assert "/insurance/issuance/client" in staff_paths
    assert not any("/guest/" in path for path in staff_paths)
    assert "/payments/{payment_id}" in payment_paths
    assert "/certificates/{certificate_id}/download" in cert_paths


def test_guest_service_is_the_only_guest_entry() -> None:
    from app.modules.guest.service import GuestService

    public = {name for name in dir(GuestService) if not name.startswith("_")}
    assert public == {
        "calculate_premium",
        "cancel_payment",
        "download_certificate",
        "ensure_client",
        "ensure_returning_client",
        "get_catalog",
        "get_payment",
        "lookup_returning_client",
        "pay",
        "submit",
    }


def test_guest_returning_client_lookup_is_masked_and_rate_limited() -> None:
    from types import SimpleNamespace

    from app.modules.guest.service import GuestService, _mask_email, _mask_name, _masked_vehicle

    for method in (GuestService.lookup_returning_client, GuestService.ensure_returning_client):
        assert "enforce_guest_identity_lookup_limit" in inspect.getsource(method)

    assert _mask_name("jane") == "J***"
    assert _mask_name("  ") == ""
    assert _mask_email("jane.doe@gmail.com") == "j***@gmail.com"

    customer = SimpleNamespace(
        id="c1",
        first_name="Jane",
        last_name="Doe",
        id_number="12345678",
        phone="+254712345678",
        email="jane@x.com",
        kra_pin="A123456789B",
        status="ACTIVE",
    )
    view = GuestService._masked_client_view(None, customer)  # type: ignore[arg-type]
    assert view["first_name"] == "J***" and view["last_name"] == "D***"
    assert view["phone"] == "+2547*****678"
    assert view["kra_pin"] is None and "Jane" not in str(view)

    vehicle = _masked_vehicle(
        SimpleNamespace(
            vehicle_registration="KDA123A",
            chassis_number="ABCDEFGH12345",
            engine_number="ENG98765",
            vehicle_year=2015,
            engine_rating=1500,
            make_code="TOY",
            vehicle_make="TOYOTA",
            model_code="AXIO",
            vehicle_model="AXIO",
        )
    )
    assert vehicle["registration"] == "KDA***A"
    assert vehicle["chassis_number"] == "*********2345"
    assert vehicle["engine_number"] == "*****765"


def test_guest_fnol_can_see_platform_staff_policies_without_peer_agencies() -> None:
    from app.modules.insurance.guest_session import guest_fnol_tenant_ids

    source = inspect.getsource(guest_fnol_tenant_ids)
    assert "DEFAULT_GUEST_AGENCY_ID" in source
    assert "is_platform" in source
    assert "Never adds a peer agency" in source


def test_guest_tenant_list_limit_is_a_short_fixed_window() -> None:
    from app.modules.insurance import guest_session

    assert guest_session.GUEST_TENANT_LIST_WINDOW <= 300
    assert guest_session.GUEST_TENANT_LIST_PER_IP >= 20
    source = inspect.getsource(guest_session.enforce_guest_tenant_list_limit)
    assert "rl:guest-tenants-v2:" in source
    assert "GUEST_TENANT_LIST_WINDOW" in source
    csrf = inspect.getsource(guest_session.enforce_guest_csrf_bootstrap_limit)
    assert "rl:guest-csrf:" in csrf


def test_guest_load_context_does_not_use_shared_hourly_api_budget() -> None:
    """Catalog + STK polls must not share one low hourly counter."""
    from app.modules.insurance import guest_session

    source = inspect.getsource(guest_session.load_guest_context)
    assert "Guest quote rate limit exceeded" not in source
    assert "rl:guest-api:" not in source
    catalog = inspect.getsource(guest_session.enforce_guest_catalog_limit)
    assert "rl:guest-catalog:" in catalog
    assert guest_session.GUEST_CATALOG_PER_IP >= 60
    assert guest_session.GUEST_PAYMENT_POLL_PER_IP >= 120


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def ttl(self, key: str) -> int:
        return self.expires.get(key, -1)

    async def expire(self, key: str, window: int) -> None:
        self.expires[key] = window


async def test_guest_rate_allow_does_not_refresh_redis_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.insurance import guest_session

    redis = _FakeRedis()
    monkeypatch.setattr(guest_session, "get_redis_client", lambda: redis)
    monkeypatch.setattr(guest_session, "redis_fail_closed", lambda: False)

    assert await guest_session._rate_allow("rl:test", limit=2, window=300)
    assert redis.expires["rl:test"] == 300
    redis.expires["rl:test"] = 120
    assert await guest_session._rate_allow("rl:test", limit=2, window=300)
    assert redis.expires["rl:test"] == 120
    assert await guest_session._rate_allow("rl:test", limit=2, window=300) is False
    assert redis.expires["rl:test"] == 120


def test_guest_jwt_can_rebuild_session_without_redis() -> None:
    from app.modules.insurance.guest_session import _session_from_jwt

    assert _session_from_jwt({"jti": "a", "tid": "b"}) is None
    rebuilt = _session_from_jwt(
        {"jti": "sess-1", "tid": "tenant-1", "dh": "devicehash", "ih": "iphash"}
    )
    assert rebuilt is not None
    assert rebuilt["jti"] == "sess-1"
    assert rebuilt["device_hash"] == "devicehash"
    assert rebuilt["from_jwt"] is True
