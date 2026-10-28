"""Phase 6 — BirdView URL tokens do not authenticate payment outcomes."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AuthenticationError
from app.integrations.payments.ports import WebhookVerificationResult
from app.modules.payments.enums import PaymentMethod, PaymentStatus
from app.modules.payments.service import PaymentService
from app.modules.payments.webhook_bind import (
    IDENTITY_CHECKOUT,
    IDENTITY_REFERENCE,
    assert_policy_accepts_settlement,
    assert_webhook_bound_to_payment,
    authenticated_payment_lookup,
    may_apply_failure,
    may_apply_success,
)
from app.modules.policies.enums import PolicyStatus


def _payment(**overrides) -> SimpleNamespace:
    values = {
        "reference": "PAY-1",
        "method": PaymentMethod.BIRDVIEW.value,
        "provider_checkout_id": "bv_stored_1",
        "tenant_id": uuid4(),
        "status": PaymentStatus.PENDING.value,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _verified(**overrides) -> WebhookVerificationResult:
    values = {
        "valid": True,
        "reference": "PAY-1",
        "checkout_id": "bv_stored_1",
        "success": True,
        "outcome_authenticated": False,
        "identity_kind": IDENTITY_REFERENCE,
    }
    values.update(overrides)
    return WebhookVerificationResult(**values)


def test_birdview_lookup_is_hmac_reference_not_body_checkout() -> None:
    kind, value = authenticated_payment_lookup(
        _verified(checkout_id="attacker-checkout", reference="PAY-HMAC")
    )
    assert kind == IDENTITY_REFERENCE
    assert value == "PAY-HMAC"


def test_mpesa_lookup_is_signed_checkout() -> None:
    kind, value = authenticated_payment_lookup(
        _verified(
            identity_kind=IDENTITY_CHECKOUT,
            checkout_id="ws_CO_real",
            reference="forged-ref",
        )
    )
    assert kind == IDENTITY_CHECKOUT
    assert value == "ws_CO_real"


def test_apply_webhook_never_prefers_unsigned_checkout() -> None:
    source = inspect.getsource(PaymentService.apply_webhook)
    assert "authenticated_payment_lookup" in source
    assert source.index("authenticated_payment_lookup") < source.index(
        "find_payment_by_reference_global"
    )
    assert "if checkout_id:" not in source


def test_unsigned_success_requires_stored_checkout_match() -> None:
    payment = _payment()
    assert_webhook_bound_to_payment(
        payment,  # type: ignore[arg-type]
        _verified(checkout_id="bv_stored_1", outcome_authenticated=False),
        method=PaymentMethod.BIRDVIEW.value,
    )
    with pytest.raises(AuthenticationError):
        assert_webhook_bound_to_payment(
            payment,  # type: ignore[arg-type]
            _verified(checkout_id="other", outcome_authenticated=False),
            method=PaymentMethod.BIRDVIEW.value,
        )
    with pytest.raises(AuthenticationError):
        assert_webhook_bound_to_payment(
            payment,  # type: ignore[arg-type]
            _verified(checkout_id=None, outcome_authenticated=False),
            method=PaymentMethod.BIRDVIEW.value,
        )


def test_unsigned_failure_is_not_terminal() -> None:
    unsigned = _verified(success=False, outcome_authenticated=False, checkout_id="bv_stored_1")
    signed = _verified(success=False, outcome_authenticated=True, checkout_id="bv_stored_1")
    assert may_apply_failure(unsigned) is False
    assert may_apply_failure(signed) is True
    assert "may_apply_failure" in inspect.getsource(PaymentService.apply_webhook)
    assert "unsigned_failure_ignored" in inspect.getsource(PaymentService.apply_webhook)


def test_unsigned_success_needs_checkout_claim() -> None:
    assert may_apply_success(_verified(success=True, checkout_id="bv_1")) is True
    assert may_apply_success(_verified(success=True, checkout_id=None)) is False
    assert (
        may_apply_success(_verified(success=True, checkout_id=None, outcome_authenticated=True))
        is True
    )


def test_checkout_cannot_retarget_another_payment() -> None:
    with pytest.raises(AuthenticationError):
        assert_webhook_bound_to_payment(
            _payment(reference="PAY-A"),  # type: ignore[arg-type]
            _verified(reference="PAY-B", checkout_id="bv_stored_1"),
            method=PaymentMethod.BIRDVIEW.value,
        )


def test_cancelled_policy_cannot_settle() -> None:
    policy = SimpleNamespace(tenant_id=uuid4(), status=PolicyStatus.CANCELLED.value)
    with pytest.raises(AuthenticationError):
        assert_policy_accepts_settlement(policy, payment_tenant_id=policy.tenant_id)
    assert_policy_accepts_settlement(
        SimpleNamespace(tenant_id=policy.tenant_id, status=PolicyStatus.PENDING_PAYMENT.value),
        payment_tenant_id=policy.tenant_id,
    )


def test_callback_ip_uses_rightmost_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security import request as request_mod

    monkeypatch.setattr(
        request_mod,
        "get_settings",
        lambda: SimpleNamespace(trust_x_forwarded_for=True, trusted_proxy_hops=1),
    )
    request = SimpleNamespace(
        headers={"x-forwarded-for": "1.1.1.1, 41.90.1.5"},
        client=SimpleNamespace(host="10.0.0.8"),
    )
    assert request_mod.client_ip(request) == "41.90.1.5"
    assert request_mod.proxy_observed_ip(request) == "41.90.1.5"
    assert request_mod.ip_in_allowlist("41.90.1.5", "41.90.0.0/16")
    assert not request_mod.ip_in_allowlist("1.1.1.1", "41.90.0.0/16")


def test_callback_ip_ignores_xff_without_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security import request as request_mod

    monkeypatch.setattr(
        request_mod, "get_settings", lambda: SimpleNamespace(trust_x_forwarded_for=False)
    )
    request = SimpleNamespace(
        headers={"x-forwarded-for": "41.90.1.5"},
        client=SimpleNamespace(host="8.8.8.8"),
    )
    assert request_mod.client_ip(request) == "8.8.8.8"


@pytest.mark.asyncio
async def test_birdview_does_not_treat_reference_as_checkout() -> None:
    from time import time

    from app.core.config import Settings
    from app.integrations.payments.birdview.provider import (
        BirdViewProvider,
        sign_birdview_callback,
    )

    provider = BirdViewProvider(Settings(birdview_webhook_secret="bv-secret"))
    exp = int(time()) + 600
    sig = sign_birdview_callback(reference="PAY-X", amount="1.00", exp=exp, secret="bv-secret")
    verified = await provider.verify_webhook(
        headers={},
        payload={
            "ref": "PAY-X",
            "sig": sig,
            "amt": "1.00",
            "exp": str(exp),
            "ResultCode": "1032",
        },
    )
    assert verified.reference == "PAY-X"
    assert verified.checkout_id is None
    assert verified.outcome_authenticated is False
    assert verified.identity_kind == IDENTITY_REFERENCE
    assert verified.success is False


@pytest.mark.asyncio
async def test_required_result_signature_covers_failure_too() -> None:
    from time import time

    from app.core.config import Settings
    from app.integrations.payments.birdview.provider import (
        BirdViewProvider,
        sign_birdview_callback,
    )

    provider = BirdViewProvider(
        Settings(
            birdview_webhook_secret="bv-secret",
            birdview_result_signature_required=True,
        )
    )
    exp = int(time()) + 600
    sig = sign_birdview_callback(reference="PAY-X", amount="1.00", exp=exp, secret="bv-secret")
    with pytest.raises(AuthenticationError):
        await provider.verify_webhook(
            headers={},
            payload={
                "ref": "PAY-X",
                "sig": sig,
                "amt": "1.00",
                "exp": str(exp),
                "ResultCode": "1032",
            },
        )
