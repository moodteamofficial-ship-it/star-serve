"""Phase 2 unit/security tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ResourceNotFoundError, ValidationAppError
from app.core.security.context import SecurityContext
from app.core.validation.identity import (
    id_number_compact,
    id_number_lookup_variants,
    normalize_id_number,
    normalize_kra_pin,
    normalize_phone,
)
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import CustomerCreateRequest, CustomerUpdateRequest
from app.modules.intermediaries.service import IntermediaryService


def test_normalize_id_and_kra() -> None:
    assert normalize_id_number(" 12345678 ") == "12345678"
    assert normalize_id_number("pvt-vq10y8jk") == "PVT-VQ10Y8JK"
    assert normalize_id_number(" PVT--VQ10Y8JK ") == "PVT-VQ10Y8JK"
    assert id_number_compact("PVT-VQ10Y8JK") == "PVTVQ10Y8JK"
    assert id_number_lookup_variants("PVT-VQ10Y8JK") == ["PVT-VQ10Y8JK", "PVTVQ10Y8JK"]
    assert id_number_lookup_variants("12345678") == ["12345678"]
    assert normalize_kra_pin("a123456789b") == "A123456789B"
    with pytest.raises(ValidationAppError):
        normalize_id_number("AB")
    with pytest.raises(ValidationAppError):
        normalize_id_number("PVT-")
    with pytest.raises(ValidationAppError):
        normalize_kra_pin("BAD")
    with pytest.raises(ValidationAppError):
        normalize_phone("123")


def test_customer_create_forbids_privileged_fields() -> None:
    with pytest.raises(ValidationError):
        CustomerCreateRequest(  # type: ignore[call-arg]
            first_name="Jane",
            last_name="Doe",
            id_number="12345678",
            phone="+254712345678",
            tenant_id=str(uuid4()),
            status="APPROVED",
        )


def test_customer_update_forbids_id_number_and_tenant() -> None:
    with pytest.raises(ValidationError):
        CustomerUpdateRequest(  # type: ignore[call-arg]
            id_number="99999999",
            tenant_id=str(uuid4()),
        )


class _ScalarSession:
    def __init__(self, value=None):
        self.value = value

    async def scalar(self, _stmt):
        return self.value

    async def scalars(self, _stmt):
        class R:
            def all(self_inner):
                return []

        return R()


@pytest.mark.asyncio
async def test_customer_get_cross_tenant_not_found() -> None:
    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@agency-a.local",
        role_id=uuid4(),
        role_code="test",
        permissions={"customer:read"},
    )
    repo = CustomerRepository(_ScalarSession(None), ctx)
    with pytest.raises(ResourceNotFoundError):
        await repo.get_active_by_id(uuid4())


@pytest.mark.asyncio
async def test_intermediary_approve_requires_pending() -> None:
    from app.modules.intermediaries.models import Intermediary

    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="admin@agency-a.local",
        role_id=uuid4(),
        role_code="test",
        permissions={"agent:approve"},
        tenant_status="ACTIVE",
    )

    class FakeRepo:
        def __init__(self):
            self.row = Intermediary(
                id=uuid4(),
                tenant_id=ctx.tenant_id,
                name="Agent",
                email="agent@example.com",
                phone="+254700000000",
                identification="12345678",
                status="SUSPENDED",
            )

        async def get_active_by_id(self, _id):
            return self.row

    service = IntermediaryService(_ScalarSession(), ctx)
    service.repo = FakeRepo()  # type: ignore[assignment]
    with pytest.raises(ValidationAppError):
        await service.approve(uuid4())
