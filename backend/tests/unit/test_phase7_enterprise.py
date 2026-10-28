"""Phase 7 unit tests — reports, resolver, settings sanitization."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.database.enums import DatabaseMode
from app.core.database.resolver import TenantDatabaseResolver
from app.modules.reports.enums import ReportType
from app.modules.reports.schemas import ReportRunRequest
from app.modules.tenants.router import TenantDatabaseModeRequest, TenantSettingsUpdateRequest


def test_report_request_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        ReportRunRequest(  # type: ignore[call-arg]
            report_type="POLICIES_SUMMARY",
            params={},
            tenant_id=str(uuid4()),
        )


def test_report_types_catalog() -> None:
    assert ReportType.POLICIES_SUMMARY.value == "POLICIES_SUMMARY"
    assert ReportType.AUDIT_ACTIVITY in ReportType


def test_tenant_settings_forbid_mass_assignment_of_db_fields_via_extra() -> None:
    with pytest.raises(ValidationError):
        TenantSettingsUpdateRequest(  # type: ignore[call-arg]
            trading_name="Agency",
            database_mode="DEDICATED_DATABASE",
        )


def test_database_mode_request_requires_reason() -> None:
    with pytest.raises(ValidationError):
        TenantDatabaseModeRequest(  # type: ignore[call-arg]
            database_mode=DatabaseMode.SHARED_DATABASE,
        )


def test_resolver_falls_back_to_shared() -> None:
    resolver = TenantDatabaseResolver()
    tid = uuid4()
    factory = resolver.session_factory(
        tenant_id=tid, mode=DatabaseMode.DEDICATED_DATABASE
    )
    assert factory is resolver.session_factory(tenant_id=tid, mode=DatabaseMode.SHARED_DATABASE)
    assert resolver.has_dedicated(tid) is False


@pytest.mark.asyncio
async def test_available_report_types_service() -> None:
    from app.core.security.context import SecurityContext
    from app.modules.reports.service import ReportService

    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@agency-a.local",
        role_id=uuid4(),
        role_code="test",
        permissions={"reports:read"},
        tenant_status="ACTIVE",
    )

    class FakeSession:
        pass

    service = ReportService(FakeSession(), ctx)  # type: ignore[arg-type]
    assert "PAYMENTS_SUMMARY" in service.available_types()
