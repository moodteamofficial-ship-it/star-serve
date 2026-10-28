"""Phase 4 proposal workflow tests."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.proposals.enums import ProposalStatus
from app.modules.proposals.schemas import ProposalCreateRequest
from app.modules.proposals.service import ProposalService, _is_double_insurance_clear


def test_proposal_create_forbids_client_premium() -> None:
    with pytest.raises(ValidationError):
        ProposalCreateRequest(  # type: ignore[call-arg]
            customer_id=str(uuid4()),
            product_code="MOTOR_COMP",
            cover_option="Comprehensive",
            cover_period="12",
            vehicle_registration="KDA123A",
            vehicle_make="TOYOTA",
            sum_insured=Decimal("1000000"),
            gross_premium=1,
        )


def test_double_insurance_clear_helpers() -> None:
    assert _is_double_insurance_clear({"hasDoubleInsurance": False}) is True
    assert _is_double_insurance_clear({"hasDoubleInsurance": True}) is False
    assert _is_double_insurance_clear({"status": "CLEAR"}) is True
    assert _is_double_insurance_clear({"status": "DETECTED"}) is False


def test_double_insurance_parser_is_shared_and_shape_tolerant() -> None:
    """The issuance wizard and the proposals path must not disagree."""
    from app.modules.insurance.policy_rules import (
        evaluate_double_insurance,
        is_double_insurance_clear as shared,
    )

    detected_shapes = [
        {"hasDoubleInsurance": True},
        {"data": {"hasDoubleInsurance": True}},
        {"data": {"hasDoubleInsurance": "true"}},
        {"hasDoubleInsurance": 1},
        {"data": {"status": "FOUND"}},
        {"message": "Vehicle has an active certificate expiring 2026-01-01"},
        {"Data": [{"hasDoubleInsurance": True}]},
    ]
    for payload in detected_shapes:
        assert evaluate_double_insurance(payload) == "DETECTED", payload
        assert shared(payload) is False, payload
        assert _is_double_insurance_clear(payload) is False, payload

    for payload in [{"hasDoubleInsurance": False}, {"data": {"status": "CLEAR"}}]:
        assert evaluate_double_insurance(payload) == "CLEAR", payload
        assert shared(payload) is True, payload


def test_unreadable_double_insurance_answer_blocks_where_enforced() -> None:
    from app.core.config import Settings
    from app.modules.insurance.policy_rules import (
        evaluate_double_insurance,
        is_double_insurance_clear,
    )

    enforced = Settings(definite_assurance_enforce_double_insurance=True)
    soft = Settings(definite_assurance_enforce_double_insurance=False)
    for payload in [{}, None, "unexpected", {"unrelated": "value"}]:
        assert evaluate_double_insurance(payload) == "UNKNOWN"
        assert is_double_insurance_clear(payload, settings=enforced) is False
        assert is_double_insurance_clear(payload, settings=soft) is True


@pytest.mark.asyncio
async def test_approve_requires_submitted() -> None:
    from app.modules.proposals.models import Proposal

    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@agency-a.local",
        role_id=uuid4(),
        role_code="test",
        permissions={"proposal:approve"},
        tenant_status="ACTIVE",
    )

    class FakeRepo:
        async def get(self, _id):
            return Proposal(
                id=uuid4(),
                tenant_id=ctx.tenant_id,
                customer_id=uuid4(),
                product_code="MOTOR",
                cover_option="TPO",
                cover_period="12",
                transaction_type="NEW",
                vehicle_registration="KDA123A",
                vehicle_make="TOYOTA",
                sum_insured=Decimal("100000"),
                status=ProposalStatus.DRAFT.value,
                double_insurance_result={},
                policy_check_result={},
            )

    class FakeProvider:
        pass

    class FakeSession:
        async def flush(self):
            return None

    service = ProposalService(FakeSession(), ctx, FakeProvider())  # type: ignore[arg-type]
    service.repo = FakeRepo()  # type: ignore[assignment]
    with pytest.raises(ValidationAppError):
        await service.approve(uuid4())
