"""Monthly referral cost sits on top of Definite's billed total."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.modules.insurance.fees import (
    MONTHLY_REFERRAL_COST,
    cover_period_from_policy,
    is_monthly_cover_period,
    monthly_referral_cost,
)


def test_monthly_referral_cost_is_fifty() -> None:
    assert MONTHLY_REFERRAL_COST == Decimal("50.00")
    assert monthly_referral_cost("Monthly") == Decimal("50.00")
    assert monthly_referral_cost("monthly") == Decimal("50.00")


def test_non_monthly_periods_have_no_referral_cost() -> None:
    assert monthly_referral_cost("Annually") == Decimal("0.00")
    assert monthly_referral_cost("2installments") == Decimal("0.00")
    assert monthly_referral_cost("Semi-Annual") == Decimal("0.00")
    assert monthly_referral_cost(None) == Decimal("0.00")


def test_monthly_detection_ignores_semi_and_installments() -> None:
    assert is_monthly_cover_period("Monthly") is True
    assert is_monthly_cover_period("2installments") is False
    assert is_monthly_cover_period("Semi-Annual") is False


def test_cover_period_from_policy_reads_submitted_summary() -> None:
    policy = SimpleNamespace(
        provider_payload_summary={"submitted": {"cover_period": "Monthly"}}
    )
    assert cover_period_from_policy(policy) == "Monthly"
    assert cover_period_from_policy(SimpleNamespace(provider_payload_summary={})) is None
