"""Unit tests for the security re-audit remediations."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions.sanitize import public_error_details
from app.modules.insurance.issuance_schemas import IssuancePayRequest
from app.modules.payments.settlement import GUEST_ALLOWED_RAILS, SettlementRail
from app.modules.roles.permissions_catalog import (
    AGENT_PERMISSIONS,
    AUDITOR_PERMISSIONS,
    FINANCE_PERMISSIONS,
    PERMISSION_CATALOG,
)


def test_guest_rails_are_birdview_only() -> None:
    assert GUEST_ALLOWED_RAILS == frozenset({SettlementRail.BIRDVIEW.value})


def test_issuance_pay_defaults_to_birdview() -> None:
    body = IssuancePayRequest(policy_id=str(uuid4()))
    assert body.method == "BIRDVIEW"


def test_issuance_pay_forbids_client_amount() -> None:
    with pytest.raises(ValidationError):
        IssuancePayRequest(  # type: ignore[call-arg]
            policy_id=str(uuid4()),
            method="BIRDVIEW",
            amount=1,
        )


def test_error_details_strip_provider_blobs() -> None:
    cleaned = public_error_details(
        [{"provider": {"secret": "x"}, "tried_periods": ["Monthly"], "raw": "{}"}]
    )
    assert cleaned == [{"tried_periods": ["Monthly"]}]


def test_reconcile_and_run_permissions_are_finance_not_agent() -> None:
    codes = {item["code"] for item in PERMISSION_CATALOG}
    assert "payment:reconcile" in codes
    assert "reports:run" in codes
    assert "payment:reconcile" in FINANCE_PERMISSIONS
    assert "payment:reconcile" not in AGENT_PERMISSIONS
    assert "reports:run" in FINANCE_PERMISSIONS
    assert "reports:run" not in AUDITOR_PERMISSIONS
    assert "reports:run" not in AGENT_PERMISSIONS


def test_wallet_factory_refuses_legacy_rail() -> None:
    from app.core.exceptions import ValidationAppError
    from app.integrations.payments.factory import get_payment_provider

    with pytest.raises(ValidationAppError):
        get_payment_provider("WALLET")


def test_overview_sql_is_tenant_scoped() -> None:
    from app.modules.overview.service import _OVERVIEW_SQL

    assert "tenant_id = CAST(:tenant_id AS uuid)" in _OVERVIEW_SQL
    assert "FROM payments\n" not in _OVERVIEW_SQL or "AS payments" in _OVERVIEW_SQL
    # Tenant-wide SQL must not name branch_id — the column may be absent and
    # Postgres still type-checks OR branches that reference it.
    assert "branch_id" not in _OVERVIEW_SQL
    assert "AS claims" in _OVERVIEW_SQL
    assert "FROM claim_followups WHERE tenant_id = CAST(:tenant_id AS uuid)" in _OVERVIEW_SQL


def test_overview_sql_platform_admin_is_cross_tenant() -> None:
    from app.modules.overview.service import _OVERVIEW_SQL, _OVERVIEW_SQL_PLATFORM

    assert "FROM claims WHERE TRUE" in _OVERVIEW_SQL_PLATFORM
    assert "FROM claim_followups WHERE TRUE" in _OVERVIEW_SQL_PLATFORM
    assert "FROM claims WHERE tenant_id = CAST(:tenant_id AS uuid)" in _OVERVIEW_SQL
    assert "branch_id" not in _OVERVIEW_SQL_PLATFORM


def test_receipt_confirm_off_in_production_by_default() -> None:
    from app.core.config import Settings

    local = "postgresql+asyncpg://starserve:starserve@localhost:5432/starserve"
    production = Settings(
        app_env="production",
        database_url=local,
        allow_insecure_production=True,
    )
    assert production.receipt_confirm_allowed is False
    assert Settings(app_env="development").receipt_confirm_allowed is True
    enabled = Settings(
        app_env="production",
        database_url=local,
        allow_receipt_confirm=True,
        allow_insecure_production=True,
    )
    assert enabled.receipt_confirm_allowed is True


@pytest.mark.asyncio
async def test_mpesa_webhook_requires_timestamp() -> None:
    from app.core.config import Settings
    from app.core.exceptions import AuthenticationError
    from app.integrations.payments.mpesa.provider import MpesaProvider

    provider = MpesaProvider(Settings(mpesa_webhook_secret="test-secret"))
    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={"X-StarServe-Signature": "abc"},
            payload={"CheckoutRequestID": "x", "Amount": "1", "ResultCode": "0"},
        )


def test_resilient_check_client_does_not_fail_open() -> None:
    import inspect

    from app.integrations.insurance.factory import ResilientInsuranceProvider

    source = inspect.getsource(ResilientInsuranceProvider.check_client)
    assert "fallback.check_client" not in source
    safety = inspect.getsource(ResilientInsuranceProvider.check_double_insurance)
    assert "_must_enforce_safety_checks" in safety


def test_staff_premium_calculate_requires_proposal_create() -> None:
    import inspect

    from app.modules.insurance import router as insurance_router

    source = inspect.getsource(insurance_router.calculate_premium)
    assert "proposal:create" in source
    assert "product:read" not in source


def test_provider_details_redact_certificate_urls() -> None:
    from app.core.security.provider_payload import redact_provider_public

    cleaned = redact_provider_public(
        {
            "status": "OK",
            "certURL": "https://blob.core.windows.net/c.pdf?sig=secret",
            "nested": {"pdfUrl": "https://example.com/a.pdf", "note": "7"},
            "page": "https://evil.example/x",
        }
    )
    assert cleaned["status"] == "OK"
    assert "certURL" not in cleaned
    assert cleaned["nested"]["note"] == "7"
    assert "pdfUrl" not in cleaned["nested"]
    assert "page" not in cleaned


def test_stale_stk_is_expired_for_retry() -> None:
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.modules.payments.enums import PaymentStatus
    from app.modules.payments.service import PaymentService

    payment = SimpleNamespace(
        method="BIRDVIEW",
        status=PaymentStatus.PENDING.value,
        created_at=datetime.now(UTC) - timedelta(minutes=4),
        version=1,
        failure_code=None,
        failure_message=None,
    )
    assert PaymentService._expire_stale_stk_attempt(PaymentService, payment) is True
    assert payment.status == PaymentStatus.FAILED.value
    assert payment.failure_code == "STK_EXPIRED"
    fresh = SimpleNamespace(
        method="BIRDVIEW",
        status=PaymentStatus.PENDING.value,
        created_at=datetime.now(UTC),
        version=1,
    )
    assert PaymentService._expire_stale_stk_attempt(PaymentService, fresh) is False


def test_reports_use_branch_predicate() -> None:
    import inspect

    from app.modules.reports.service import ReportService

    source = inspect.getsource(ReportService)
    assert "apply_branch_predicate" in source
    assert "branch:all" not in source or "apply_branch_predicate" in source
