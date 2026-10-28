"""Issuance settlement rails — single source of truth for pay → Definite → cert.

Definite ``initiatePayment`` PaymentMethod codes (insurer API):
  0 = Already paid to paybill
  1 = M-Pesa STK prompt
  3 = Wallet payment
  4 = Credit facility

StarServe rails:
  DEFINITE_WALLET  → Definite method 3 at pay time. The insurer debits agency
                     float synchronously, so HTTP success *is* settlement.
                     Requires ``wallet:debit`` — spending agency money is not
                     an ordinary ``payment:create`` action.
  DEFINITE_MPESA   → Definite method 1 at pay time. Definite sends the STK and
                     waits for Safaricom. The local payment stays PENDING until
                     Definite replies that the note is approved (e.g. "Policy
                     Approved. Proceed to Issue cert"). There is no StarServe
                     webhook — finance receipt confirm is only a fallback.
  BIRDVIEW         → BirdView STK first; after confirmed SUCCESS, Definite
                     method 3 once (wallet deduct) then certificate.

Only ``settles_on_initiate`` rails may transition a local payment to SUCCESS
without independent confirmation. Provider HTTP 200 on a customer-funded rail
is never proof that the customer paid.

Idempotency is enforced by ``provider_payment_approved`` on the policy summary
so initiatePayment cannot run twice for the same note.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Literal


class DefinitePaymentMethod(IntEnum):
    ALREADY_PAID = 0
    MPESA_STK = 1
    WALLET = 3
    CREDIT = 4


class SettlementRail(StrEnum):
    DEFINITE_WALLET = "DEFINITE_WALLET"
    DEFINITE_MPESA = "DEFINITE_MPESA"
    BIRDVIEW = "BIRDVIEW"


# Canonical rails only. Ambiguous legacy names ("MPESA", "WALLET") are refused:
# they used to resolve onto a rail that marked payments SUCCESS locally, so a
# client that omitted or mistyped the method silently bought a settled payment.
_RAIL_ALIASES: dict[str, SettlementRail] = {
    SettlementRail.DEFINITE_WALLET.value: SettlementRail.DEFINITE_WALLET,
    SettlementRail.DEFINITE_MPESA.value: SettlementRail.DEFINITE_MPESA,
    SettlementRail.BIRDVIEW.value: SettlementRail.BIRDVIEW,
}


@dataclass(frozen=True, slots=True)
class SettlementPlan:
    rail: SettlementRail
    label: str
    requires_phone: bool
    """BirdView (or similar) local STK before Definite settlement."""
    local_async_stk: bool
    """Definite initiatePayment code used when approving the proposal note."""
    definite_payment_method: DefinitePaymentMethod
    """When Definite initiatePayment runs relative to local payment SUCCESS."""
    definite_settle_phase: Literal["at_pay", "after_local_success"]
    """True only when the provider call itself moves money (agency float).

    Customer-funded rails are False: an accepted STK *request* is not a payment,
    so the local row stays PENDING until a verified confirmation arrives.
    """
    settles_on_initiate: bool = False
    """Permission required in addition to ``payment:create``.

    Float-funded rails spend agency money and must not be reachable by every
    principal that can start a customer-funded payment.
    """
    required_permission: str | None = None


PLANS: dict[SettlementRail, SettlementPlan] = {
    SettlementRail.DEFINITE_WALLET: SettlementPlan(
        rail=SettlementRail.DEFINITE_WALLET,
        label="Definite Wallet",
        requires_phone=False,
        local_async_stk=False,
        definite_payment_method=DefinitePaymentMethod.WALLET,
        definite_settle_phase="at_pay",
        # Method 3 debits agency float inside the insurer call itself.
        settles_on_initiate=True,
        required_permission="wallet:debit",
    ),
    SettlementRail.DEFINITE_MPESA: SettlementPlan(
        rail=SettlementRail.DEFINITE_MPESA,
        label="Definite M-Pesa Push",
        requires_phone=True,
        local_async_stk=False,
        definite_payment_method=DefinitePaymentMethod.MPESA_STK,
        definite_settle_phase="at_pay",
        # Method 1: STK is not settlement. SUCCESS only after Definite confirms.
        settles_on_initiate=False,
    ),
    SettlementRail.BIRDVIEW: SettlementPlan(
        rail=SettlementRail.BIRDVIEW,
        label="BirdView M-Pesa Push",
        requires_phone=True,
        local_async_stk=True,
        # After BirdView confirms cash, settle insurer float once (wallet).
        definite_payment_method=DefinitePaymentMethod.WALLET,
        definite_settle_phase="after_local_success",
        settles_on_initiate=False,
    ),
}

ASYNC_LOCAL_STK_RAILS: frozenset[str] = frozenset(
    {p.rail.value for p in PLANS.values() if p.local_async_stk}
)

# Rails whose local payment must stay PENDING until an independent confirmation
# (signed provider callback, or a finance reconcile against the provider).
AWAIT_CONFIRMATION_RAILS: frozenset[str] = frozenset(
    {p.rail.value for p in PLANS.values() if not p.settles_on_initiate}
)

# Guests may only use customer-funded STK that stays PENDING until a signed webhook.
# DEFINITE_MPESA is staff-only: Definite initiatePayment HTTP success is not proof of pay.
GUEST_ALLOWED_RAILS: frozenset[str] = frozenset({SettlementRail.BIRDVIEW.value})


def resolve_settlement_plan(method: str) -> SettlementPlan:
    from app.core.exceptions import ValidationAppError

    key = (method or "").strip().upper()
    rail = _RAIL_ALIASES.get(key)
    if rail is None:
        raise ValidationAppError(
            "Supported payment methods: DEFINITE_WALLET, DEFINITE_MPESA, BIRDVIEW"
        )
    return PLANS[rail]
