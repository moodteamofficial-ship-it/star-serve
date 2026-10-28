"""Phase 3 — guests cannot invoke arbitrary Definite operations."""

from __future__ import annotations

import inspect
from typing import Any
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.guest.insurance_gateway import GuestInsuranceGateway
from app.modules.guest.service import GuestService


class _RecordingProvider(InsuranceProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def check_client(self, *, id_number: str) -> dict[str, Any] | None:
        self.calls.append(("check_client", id_number))
        return None

    async def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_client", payload))
        return payload

    async def check_intermediary(self, *, identification: str) -> dict[str, Any] | None:
        self.calls.append(("check_intermediary", identification))
        return None

    async def register_intermediary(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("register_intermediary", payload))
        return payload

    async def get_products(self) -> list[dict[str, Any]]:
        return []

    async def get_makes(self) -> list[dict[str, Any]]:
        return []

    async def get_cancellation_reasons(self) -> list[dict[str, Any]]:
        self.calls.append(("get_cancellation_reasons", None))
        return []

    async def calculate_premium(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("calculate_premium", params))
        return {"gross_premium": 1}

    async def check_policy(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("check_policy", params))
        return params

    async def check_double_insurance(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("check_double_insurance", params))
        return params

    async def check_wallet_balance(self, *, agent_code: str) -> dict[str, Any]:
        self.calls.append(("check_wallet_balance", agent_code))
        return {"balance": 99}

    async def create_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_proposal", payload))
        return payload

    async def get_policy_details(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("get_policy_details", params))
        return params

    async def initiate_provider_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("initiate_provider_payment", payload))
        return payload

    async def generate_certificate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("generate_certificate", payload))
        return payload

    async def cancel_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("cancel_policy", payload))
        return payload


def _gateway() -> tuple[GuestInsuranceGateway, _RecordingProvider]:
    inner = _RecordingProvider()
    return GuestInsuranceGateway(inner), inner


async def test_guest_gateway_denies_privileged_definite_operations() -> None:
    gateway, inner = _gateway()
    with pytest.raises(AuthorizationError):
        await gateway.check_wallet_balance(agent_code="114181")
    with pytest.raises(AuthorizationError):
        await gateway.check_intermediary(identification="123")
    with pytest.raises(AuthorizationError):
        await gateway.register_intermediary({"name": "x"})
    with pytest.raises(AuthorizationError):
        await gateway.get_cancellation_reasons()
    with pytest.raises(AuthorizationError):
        await gateway.get_policy_details({"policyId": "1"})
    with pytest.raises(AuthorizationError):
        await gateway.cancel_policy({"policyId": "1"})
    assert inner.calls == []


async def test_guest_gateway_fails_closed_without_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings
    from app.core.exceptions import ValidationAppError

    settings = Settings(definite_assurance_agent_code="")
    monkeypatch.setattr(
        "app.core.security.provider_config.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.guest.insurance_gateway.get_settings", lambda: settings
    )
    gateway, inner = _gateway()
    with pytest.raises(ValidationAppError, match="not configured"):
        await gateway.create_proposal({"Registration": "KAA123A", "agent": "HACKED"})
    assert inner.calls == []


async def test_guest_gateway_strips_untrusted_proposal_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    settings = Settings(definite_assurance_agent_code="AGENT-9")
    monkeypatch.setattr(
        "app.core.security.provider_config.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.modules.guest.insurance_gateway.get_settings", lambda: settings
    )
    gateway, inner = _gateway()
    await gateway.create_proposal(
        {
            "Client": "not-an-oid",
            "PolicyHolder": "also-bad",
            "agent": "HACKED",
            "Registration": "KAA123A",
            "tenant_id": str(uuid4()),
            "PaymentMethod": 0,
        }
    )
    forwarded = inner.calls[0][1]
    assert forwarded["agent"] == "AGENT-9"
    assert "Client" not in forwarded
    assert "PolicyHolder" not in forwarded
    assert "tenant_id" not in forwarded
    assert "PaymentMethod" not in forwarded

    inner.calls.clear()
    await gateway.create_proposal(
        {
            "Client": "55555",
            "PolicyHolder": "55555",
            "agent": "HACKED",
            "Registration": "KAA123A",
        }
    )
    trusted = inner.calls[0][1]
    assert trusted["Client"] == 55555
    assert trusted["PolicyHolder"] == 55555
    assert trusted["agent"] == "AGENT-9"


async def test_guest_gateway_rejects_already_paid_and_credit_settlement() -> None:
    gateway, inner = _gateway()
    with pytest.raises(AuthorizationError):
        await gateway.initiate_provider_payment(
            {"noteOID": 1, "AmountPaid": 10, "PaymentMethod": 0}
        )
    with pytest.raises(AuthorizationError):
        await gateway.initiate_provider_payment(
            {"noteOID": 1, "AmountPaid": 10, "PaymentMethod": 4}
        )
    assert inner.calls == []
    await gateway.initiate_provider_payment(
        {"noteOID": 7, "AmountPaid": 10, "PaymentMethod": 3, "APIUser": "attacker"}
    )
    forwarded = inner.calls[0][1]
    assert forwarded["PaymentMethod"] == 3
    assert forwarded["noteOID"] == 7
    assert forwarded.get("APIUser") != "attacker"


def test_guest_submit_rechecks_definite_identity() -> None:
    source = inspect.getsource(GuestService.submit)
    assert "_assert_guest_created_definite_identity" in source
    assert "_guest_issuance_view" in source


def test_guest_pay_uses_the_same_issuance_redaction_as_submit() -> None:
    source = inspect.getsource(GuestService.pay)
    assert "_guest_issuance_view" in source
    assert "return await self._issuance().pay" not in source


def test_guest_issuance_view_strips_provider_ids_from_pay_payload() -> None:
    service = GuestService.__new__(GuestService)
    redacted = service._guest_issuance_view(
        {
            "payment": {"id": "pay-1", "status": "PENDING"},
            "policy": {
                "id": "pol-1",
                "policy_number": "POL-1",
                "agent_code": "991100",
                "external_policy_ref": "555",
                "provider_note_oid": "777",
                "provider_insured_item": "888",
                "provider_payment_txn": "TXN",
            },
            "certificate": None,
            "provider": {
                "proposal_oid": "555",
                "note_oid": "777",
                "document_number": "DOC-1",
                "amount_to_pay": 10,
            },
        }
    )
    policy = redacted["policy"]
    assert policy["policy_number"] == "POL-1"
    assert "agent_code" not in policy
    assert "external_policy_ref" not in policy
    assert "provider_note_oid" not in policy
    assert "provider_insured_item" not in policy
    assert "provider_payment_txn" not in policy
    assert redacted["provider"] == {"document_number": "DOC-1", "amount_to_pay": 10}
    assert redacted["payment"]["id"] == "pay-1"


def test_guest_service_always_wraps_the_provider() -> None:
    source = inspect.getsource(GuestService.__init__)
    assert "GuestInsuranceGateway" in source


def test_guest_router_does_not_hand_raw_provider_to_issuance() -> None:
    from app.modules.guest import router as guest_router

    source = inspect.getsource(guest_router)
    assert "GuestService" in source
    assert "IssuanceService(" not in source
    assert "CertificateService(" not in source
    assert "check_wallet_balance" not in source
