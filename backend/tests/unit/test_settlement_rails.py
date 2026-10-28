"""Settlement rail mapping and Definite PaymentMethod codes."""

import pytest

from app.core.exceptions import ValidationAppError
from app.modules.payments.settlement import (
    AWAIT_CONFIRMATION_RAILS,
    DefinitePaymentMethod,
    GUEST_ALLOWED_RAILS,
    SettlementRail,
    resolve_settlement_plan,
)


def test_resolve_definite_wallet_maps_to_method_3() -> None:
    plan = resolve_settlement_plan("DEFINITE_WALLET")
    assert plan.rail is SettlementRail.DEFINITE_WALLET
    assert plan.definite_payment_method is DefinitePaymentMethod.WALLET
    assert plan.definite_settle_phase == "at_pay"
    assert plan.local_async_stk is False


def test_definite_wallet_is_the_only_rail_that_settles_inline() -> None:
    """Agency float moves inside the insurer call; customer-funded rails do not."""
    assert resolve_settlement_plan("DEFINITE_WALLET").settles_on_initiate is True
    assert resolve_settlement_plan("DEFINITE_MPESA").settles_on_initiate is False
    assert resolve_settlement_plan("BIRDVIEW").settles_on_initiate is False
    assert AWAIT_CONFIRMATION_RAILS == frozenset(
        {SettlementRail.DEFINITE_MPESA.value, SettlementRail.BIRDVIEW.value}
    )


def test_float_funded_rail_requires_wallet_debit() -> None:
    assert resolve_settlement_plan("DEFINITE_WALLET").required_permission == "wallet:debit"
    assert resolve_settlement_plan("DEFINITE_MPESA").required_permission is None
    assert resolve_settlement_plan("BIRDVIEW").required_permission is None


def test_resolve_definite_mpesa_maps_to_method_1() -> None:
    plan = resolve_settlement_plan("DEFINITE_MPESA")
    assert plan.rail is SettlementRail.DEFINITE_MPESA
    assert plan.definite_payment_method is DefinitePaymentMethod.MPESA_STK
    assert plan.requires_phone is True
    assert plan.definite_settle_phase == "at_pay"


def test_resolve_birdview_settles_wallet_after_local_success() -> None:
    plan = resolve_settlement_plan("BIRDVIEW")
    assert plan.rail is SettlementRail.BIRDVIEW
    assert plan.local_async_stk is True
    assert plan.definite_payment_method is DefinitePaymentMethod.WALLET
    assert plan.definite_settle_phase == "after_local_success"


@pytest.mark.parametrize("method", ["MPESA", "WALLET", "", "definite", "CARD"])
def test_ambiguous_and_legacy_methods_are_refused(method: str) -> None:
    """These used to resolve onto a rail that marked the payment SUCCESS locally."""
    with pytest.raises(ValidationAppError):
        resolve_settlement_plan(method)


@pytest.mark.asyncio
async def test_definite_sync_provider_only_settles_the_wallet_rail() -> None:
    from decimal import Decimal

    from app.integrations.payments.definite_sync.provider import DefiniteSyncPaymentProvider

    provider = DefiniteSyncPaymentProvider()

    wallet = await provider.initiate(
        reference="PAY-W",
        amount=Decimal("100.00"),
        currency="KES",
        phone=None,
        metadata={"settlement_rail": "DEFINITE_WALLET"},
    )
    assert wallet.status == "SUCCESS"

    stk = await provider.initiate(
        reference="PAY-M",
        amount=Decimal("100.00"),
        currency="KES",
        phone="254700000000",
        metadata={"settlement_rail": "DEFINITE_MPESA"},
    )
    assert stk.status == "PENDING"
    assert stk.receipt is None

    # Missing/unknown rail must fail closed rather than mint a settled payment.
    unknown = await provider.initiate(
        reference="PAY-U",
        amount=Decimal("100.00"),
        currency="KES",
        phone=None,
        metadata={},
    )
    assert unknown.status == "PENDING"


def test_definite_note_confirmed_requires_approval_phrase() -> None:
    from app.modules.insurance.definite_settlement import (
        definite_note_confirmed,
        policy_note_confirmed,
    )

    assert definite_note_confirmed(
        {"success": True, "message": "Policy Approved. Proceed to Issue cert"}
    )
    assert definite_note_confirmed({"message": "Already paid for this note"})
    assert not definite_note_confirmed({"success": True, "message": "STK prompt sent"})
    assert not definite_note_confirmed({"success": True})
    assert not definite_note_confirmed({"success": False, "message": "duplicate"})
    assert policy_note_confirmed(
        {
            "provider_payment_approved": True,
            "provider_payment_response": {
                "success": True,
                "message": "Policy Approved. Proceed to Issue cert",
            },
        }
    )
    assert policy_note_confirmed({"provider_payment_confirmed": True})
    assert not policy_note_confirmed(
        {
            "provider_payment_approved": True,
            "provider_payment_response": {"success": True, "message": "STK prompt sent"},
        }
    )


def test_payment_get_syncs_definite_stk_confirmation() -> None:
    import inspect

    from app.modules.insurance.issuance_service import IssuanceService
    from app.modules.payments.service import PaymentService

    get_src = inspect.getsource(PaymentService.get)
    initiate_src = inspect.getsource(PaymentService.initiate)
    pay_src = inspect.getsource(IssuanceService.pay)
    assert "sync_definite_stk_confirmation" in get_src
    assert "definite_confirmed" in initiate_src
    assert "sync_definite_stk_confirmation" in pay_src


def test_guests_cannot_use_agency_wallet_rail() -> None:
    assert SettlementRail.DEFINITE_WALLET.value not in GUEST_ALLOWED_RAILS
    assert SettlementRail.BIRDVIEW.value in GUEST_ALLOWED_RAILS
    assert SettlementRail.DEFINITE_MPESA.value not in GUEST_ALLOWED_RAILS
