"""Premiums are priced for exactly the period the user chose, in Definite's vocabulary."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationAppError
from app.integrations.insurance.definite_assurance.exceptions import (
    DefiniteAssuranceValidationError,
)
from app.integrations.insurance.definite_assurance.service import (
    DefiniteAssuranceProvider,
    definite_cover_period,
)
from app.modules.insurance.issuance_service import _cover_days, _payment_interval


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Monthly", "Monthly"),
        ("monthly", "Monthly"),
        ("2installments", "2installments"),
        ("Semi-Annual", "2installments"),
        ("Annual", "Annually"),
        ("Annually", "Annually"),
    ],
)
def test_periods_map_to_definite_values(given: str, expected: str) -> None:
    assert definite_cover_period(given) == expected
    assert _payment_interval(given) == expected


@pytest.mark.parametrize("bad", ["Quarterly", "", "12"])
def test_unsupported_period_is_rejected(bad: str) -> None:
    with pytest.raises(ValidationAppError):
        definite_cover_period(bad)


def test_cover_days() -> None:
    assert _cover_days("Monthly") == 30
    assert _cover_days("2installments") == 180
    assert _cover_days("Annually") == 365


class _Client:
    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def get(self, path: str, params: dict | None = None, retryable: bool = False):
        self.calls.append(dict(params or {}))
        return self.reply


_PARAMS = {
    "sum_insured": 0,
    "capacity": 2,
    "tonnage": 0,
    "product": "4652",
    "cover_option": "3535",
    "transaction_type": "1",
}


@pytest.mark.asyncio
async def test_monthly_is_priced_at_the_amount_definite_bills() -> None:
    client = _Client(
        {"basicPremium": 500, "PHCF": 1, "trainingLevy": 1, "stampDuty": 40, "grossPremium": 542}
    )
    result = await DefiniteAssuranceProvider(client).calculate_premium(
        {**_PARAMS, "cover_period": "Monthly"}
    )
    assert [call["coverPeriod"] for call in client.calls] == ["Annually"]
    assert result["gross_premium"] == 542
    assert result["cover_period_used"] == "Monthly"


@pytest.mark.asyncio
async def test_semi_annual_is_priced_as_chosen() -> None:
    client = _Client(
        {"basicPremium": 1000, "PHCF": 3, "trainingLevy": 2, "stampDuty": 40, "grossPremium": 1045}
    )
    result = await DefiniteAssuranceProvider(client).calculate_premium(
        {**_PARAMS, "cover_period": "2installments"}
    )
    assert [call["coverPeriod"] for call in client.calls] == ["2installments"]
    assert result["cover_period_used"] == "2installments"


@pytest.mark.asyncio
async def test_no_price_is_an_error_not_a_different_period() -> None:
    client = _Client({"stampDuty": 40, "grossPremium": None})
    with pytest.raises(DefiniteAssuranceValidationError):
        await DefiniteAssuranceProvider(client).calculate_premium(
            {**_PARAMS, "cover_period": "Annual"}
        )
    assert [call["coverPeriod"] for call in client.calls] == ["Annually"]
