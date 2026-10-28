"""Guards for the SS3 remediations — one assertion per leftover attack."""

import pytest

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.core.security.crypto import assert_dedicated_dsn_allowed, decrypt_secret, is_fernet_token
from app.modules.payments.settlement import AWAIT_CONFIRMATION_RAILS, SettlementRail


def test_customer_funded_rails_await_confirmation() -> None:
    assert SettlementRail.DEFINITE_MPESA.value in AWAIT_CONFIRMATION_RAILS
    assert SettlementRail.BIRDVIEW.value in AWAIT_CONFIRMATION_RAILS
    assert SettlementRail.DEFINITE_WALLET.value not in AWAIT_CONFIRMATION_RAILS


def test_guest_signing_key_is_not_the_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.modules.insurance import guest_session

    get_settings.cache_clear()
    settings = Settings(
        encryption_key="encryption-material-must-not-sign-guests!!",
        guest_signing_secret="dedicated-guest-hmac-secret",
        csrf_secret="unused-csrf",
    )
    monkeypatch.setattr(guest_session, "get_settings", lambda: settings)
    key_a = guest_session._guest_signing_key()
    other = Settings(
        encryption_key="encryption-material-must-not-sign-guests!!",
        guest_signing_secret="a-different-guest-secret",
        csrf_secret="unused-csrf",
    )
    monkeypatch.setattr(guest_session, "get_settings", lambda: other)
    key_b = guest_session._guest_signing_key()
    assert key_a != key_b


def test_guest_signing_key_refuses_encryption_fallback_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.insurance import guest_session

    settings = Settings(
        app_env="production",
        allow_insecure_production=False,
        guest_signing_secret="",
        encryption_key="x" * 32,
        csrf_secret="y" * 32,
    )
    monkeypatch.setattr(guest_session, "get_settings", lambda: settings)
    with pytest.raises(AuthenticationError):
        guest_session._guest_signing_key()


def test_staff_auth_does_not_accept_guest_sessions() -> None:
    import inspect

    from app.core.dependencies import auth

    assert not hasattr(auth, "require_staff_or_guest")
    source = inspect.getsource(auth.require_permissions)
    assert "load_guest_context" not in source
    assert "require_staff_principal" in source


def test_auth_bind_sql_requires_token_tenant() -> None:
    from app.core.dependencies.auth import _AUTH_BIND_AND_CHECK

    sql = str(_AUTH_BIND_AND_CHECK)
    assert "u.tenant_id = CAST(:tid AS uuid)" in sql
    assert "set_config('app.tenant_id', CAST(:tid AS text), true)" in sql


def test_unknown_login_still_runs_argon2() -> None:
    from app.core.security.passwords import verify_password
    from app.modules.auth.service import _DUMMY_PASSWORD_HASH

    assert verify_password("timing-pad-never-a-real-password!!", _DUMMY_PASSWORD_HASH)
    assert not verify_password("wrong-password-guess", _DUMMY_PASSWORD_HASH)


def test_csrf_does_not_skip_when_cookie_session_is_present() -> None:
    from app.core.middleware.csrf import CsrfMiddleware

    source = CsrfMiddleware.dispatch.__code__.co_consts
    joined = " ".join(str(item) for item in source if isinstance(item, str))
    # The skip is gated on the absence of both session and guest cookies.
    assert "has_session_cookie" in CsrfMiddleware.dispatch.__code__.co_varnames
    assert "has_guest_cookie" in CsrfMiddleware.dispatch.__code__.co_varnames
    _ = joined


def test_password_login_is_csrf_bootstrap() -> None:
    import inspect

    from app.core.middleware.csrf import CsrfMiddleware, _is_password_login

    source = inspect.getsource(CsrfMiddleware.dispatch)
    assert "_is_password_login" in source
    from starlette.requests import Request

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
        }
    )
    assert _is_password_login(req) is True
    other = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/logout",
            "headers": [],
        }
    )
    assert _is_password_login(other) is False


def test_login_does_not_mask_lock_or_reject_matching_legacy_secrets() -> None:
    import inspect

    from app.modules.auth.service import AuthService

    source = inspect.getsource(AuthService.authenticate)
    lock_block = source.split("except LoginLockedError:", 1)[1].split("user =", 1)[0]
    assert "raise invalid" not in lock_block
    assert "legacy_weak_password" in source
    assert 'metadata={"reason": "forbidden_password"}' not in source


def test_plaintext_dsn_is_not_an_envelope() -> None:
    dsn = "postgresql+asyncpg://u:p@evil.example:5432/starserve"
    assert not is_fernet_token(dsn)
    with pytest.raises(ValueError):
        decrypt_secret(dsn, require_envelope=True)
    with pytest.raises(ValueError):
        assert_dedicated_dsn_allowed(dsn)


@pytest.mark.asyncio
async def test_production_definite_settlement_refuses_zero_amount_and_test_phone() -> None:
    from app.integrations.insurance.definite_assurance.service import (
        DefiniteAssuranceProvider,
    )

    class _Client:
        async def post(self, *args, **kwargs):  # noqa: ANN002
            raise AssertionError("must not call Definite")

    provider = DefiniteAssuranceProvider(_Client())  # type: ignore[arg-type]
    from unittest.mock import patch

    from app.core.config import Settings as S

    production = S(
        app_env="production",
        allow_insecure_production=True,
        definite_assurance_test_phone="254700000001",
        definite_assurance_base_url="https://api.definiteassurance.com/api/v1",
    )

    with patch("app.core.config.get_settings", return_value=production):
        with pytest.raises(ValidationAppError):
            await provider.initiate_provider_payment(
                {"AmountPaid": 0, "PhoneNumber": "254711111111", "noteOID": 1}
            )
        with pytest.raises(ValidationAppError):
            await provider.initiate_provider_payment({"AmountPaid": 1949, "noteOID": 1})


@pytest.mark.asyncio
async def test_non_production_wallet_never_sends_full_premium() -> None:
    from unittest.mock import patch

    from app.core.config import Settings as S
    from app.integrations.insurance.definite_assurance.service import (
        DefiniteAssuranceProvider,
    )
    from app.modules.payments.settlement import DefinitePaymentMethod

    captured: dict = {}

    class _Client:
        async def post(self, path, *, json_body):  # noqa: ANN003
            captured.update(json_body)
            return {"success": True, "message": "Policy Approved. Proceed to Issue cert"}

    staging = S(
        app_env="staging",
        definite_assurance_base_url="https://uat.definiteassurance.com/api/v1",
        definite_assurance_username="agent",
        birdview_test_amount=500,
    )
    provider = DefiniteAssuranceProvider(_Client())  # type: ignore[arg-type]
    with patch("app.core.config.get_settings", return_value=staging):
        await provider.initiate_provider_payment(
            {
                "AmountPaid": 1949,
                "PaymentMethod": int(DefinitePaymentMethod.WALLET),
                "PhoneNumber": "254711111111",
                "noteOID": 11,
                "Proposal": 22,
                "InsuredItem": 33,
                "DocumentNumber": "DOC-1",
            }
        )
    assert captured["AmountPaid"] == "1"
    assert captured["PaymentMethod"] == int(DefinitePaymentMethod.WALLET)


def test_guest_tenants_list_does_not_insert() -> None:
    import inspect

    from app.modules.insurance.guest_session import list_guest_tenants

    source = inspect.getsource(list_guest_tenants)
    assert "ensure_default_guest_agency" not in source


def _http_request(headers: dict[str, str]):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/insurance/catalog",
            "headers": [
                (key.lower().encode(), value.encode()) for key, value in headers.items()
            ],
        }
    )


def test_guest_origin_accepts_same_origin_get_via_referer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.exceptions import AuthorizationError
    from app.modules.insurance import guest_session

    settings = Settings(cors_origins="http://localhost:5173")
    monkeypatch.setattr(guest_session, "get_settings", lambda: settings)

    recovered = guest_session.require_trusted_origin(
        _http_request(
            {
                "sec-fetch-site": "same-origin",
                "referer": "http://localhost:5173/welcome",
            }
        )
    )
    assert recovered == "http://localhost:5173"

    explicit = guest_session.require_trusted_origin(
        _http_request({"origin": "http://localhost:5173"})
    )
    assert explicit == "http://localhost:5173"

    with pytest.raises(AuthorizationError, match="Trusted guest origin"):
        guest_session.require_trusted_origin(_http_request({}))

    with pytest.raises(AuthorizationError, match="Trusted guest origin"):
        guest_session.require_trusted_origin(
            _http_request(
                {
                    "sec-fetch-site": "cross-site",
                    "referer": "http://localhost:5173/welcome",
                }
            )
        )

    with pytest.raises(AuthorizationError, match="not allowed"):
        guest_session.require_trusted_origin(
            _http_request({"origin": "https://evil.example"})
        )

    with pytest.raises(AuthorizationError, match="Trusted guest origin"):
        guest_session.require_trusted_origin(_http_request({"origin": "null"}))


def test_overview_sql_keeps_where_after_tenant_scope() -> None:
    from app.modules.overview.service import _OVERVIEW_SQL, _scope_overview_sql

    scoped = _scope_overview_sql(
        "SELECT 1 FROM payments WHERE created_at >= :start GROUP BY 1 ORDER BY 1"
    )
    assert "AS payments WHERE created_at >= :start GROUP BY 1 ORDER BY 1" in scoped
    assert "AS payments created_at" not in scoped
    assert "AS payments BY " not in _OVERVIEW_SQL
    assert "AS payments created_at" not in _OVERVIEW_SQL
    assert "AS payments\n    WHERE created_at >= :start AND created_at <= :end" in _OVERVIEW_SQL


def test_overview_sql_branch_scope_is_fail_closed() -> None:
    from uuid import uuid4

    from app.core.security.branch_scope import BranchScope
    from app.core.security.context import SecurityContext
    from app.modules.overview.service import (
        _OVERVIEW_SQL_BY_SCOPE,
        _overview_branch_mode,
        _scope_overview_sql,
    )

    tenant_wide = _OVERVIEW_SQL_BY_SCOPE[BranchScope.ALL_TENANT]
    assigned = _OVERVIEW_SQL_BY_SCOPE[BranchScope.ASSIGNED]
    none = _OVERVIEW_SQL_BY_SCOPE[BranchScope.NONE]
    sample = "SELECT 1 FROM payments WHERE created_at >= :start"

    assert "branch_id" not in tenant_wide
    assert "branch_id" not in _scope_overview_sql(sample, BranchScope.ALL_TENANT)
    assert "AND FALSE" not in tenant_wide

    assert "branch_id IS NOT NULL" in assigned
    assert "ANY(CAST(:branch_ids AS uuid[]))" in assigned
    assert "string_to_array" not in assigned
    assert "branch_ids_csv" not in assigned
    assert str(uuid4()) not in assigned

    assert "AND FALSE" in none
    assert "branch_id" not in none
    assert "AND FALSE" in _scope_overview_sql(sample, BranchScope.NONE)

    admin = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@agency.local",
        role_id=uuid4(),
        role_code="agency_admin",
        permissions={"branch:all"},
        branch_scope=BranchScope.ALL_TENANT,
        branch_ids=set(),
    )
    agent = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="agent@agency.local",
        role_id=uuid4(),
        role_code="agent",
        permissions={"payment:read"},
        branch_scope=BranchScope.ASSIGNED,
        branch_ids={uuid4()},
    )
    empty = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="none@agency.local",
        role_id=uuid4(),
        role_code="agent",
        permissions={"payment:read"},
        branch_scope=BranchScope.NONE,
        branch_ids=set(),
    )
    guest = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="guest@agency.local",
        role_id=uuid4(),
        role_code="guest",
        permissions=set(),
        is_guest=True,
        branch_scope=BranchScope.NONE,
        branch_ids=set(),
    )
    assert _overview_branch_mode(admin) is BranchScope.ALL_TENANT
    assert _overview_branch_mode(agent) is BranchScope.ASSIGNED
    assert _overview_branch_mode(empty) is BranchScope.NONE
    assert _overview_branch_mode(guest) is BranchScope.ALL_TENANT


def test_overview_shapes_claims_and_followups() -> None:
    from datetime import UTC, datetime

    from app.modules.overview.service import _shape_claims, _shape_followups

    claims = _shape_claims(
        {
            "by_status": {
                "CLAIM_SUBMITTED": 2,
                "VETTING": 1,
                "DEFINITE_REVIEW": 3,
                "PAYMENT_PENDING": 1,
                "CLOSED": 4,
            },
            "open": 7,
            "unassigned": 2,
            "guest_intake": 1,
            "created_in_period": 3,
            "closed_in_period": 1,
            "claimed_open": "250000",
            "currency": "KES",
            "week": {},
        },
        end=datetime(2026, 9, 13, tzinfo=UTC),
    )
    assert claims["intake"] == 2
    assert claims["assessing"] == 1
    assert claims["with_insurer"] == 3
    assert claims["settling"] == 1
    assert claims["closed"] == 4
    assert claims["assigned"] == 5
    assert claims["claimed_open"] == 250000.0
    assert [row["key"] for row in claims["queues"]] == ["intake", "assessing", "insurer", "settling"]
    assert claims["recent"] == []

    followups = _shape_followups(
        {
            "open": 5,
            "overdue": 2,
            "due_soon": 1,
            "waiting_client": 3,
            "waiting_desk": 2,
            "completed_in_period": 4,
            "created_in_period": 6,
            "by_type": [{"type": "CLIENT_INFORMATION", "count": 3}],
        }
    )
    assert followups["overdue"] == 2
    assert followups["total"] == 0
    assert followups["by_type"][0]["label"] == "Client"
    assert followups["recent"] == []
