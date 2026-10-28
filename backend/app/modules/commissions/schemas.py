"""Commission API schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.commissions.enums import PayoutCadence


class CommissionSettingsUpdateRequest(BaseModel):
    certificate_rate_percent: Decimal = Field(ge=0, le=100, decimal_places=4)
    claim_rate_percent: Decimal = Field(ge=0, le=100, decimal_places=4)
    payout_cadence: str = Field(max_length=16)
    enabled: bool = True
    notes: str | None = Field(default=None, max_length=2000)
    currency: str = Field(default="KES", max_length=8)
    customer_referral_amount: Decimal | None = Field(
        default=None, ge=0, le=100000, decimal_places=2
    )
    customer_referrals_enabled: bool | None = None

    model_config = {"extra": "forbid"}

    @field_validator("payout_cadence")
    @classmethod
    def validate_cadence(cls, value: str) -> str:
        key = value.strip().upper()
        if key not in {PayoutCadence.WEEKLY.value, PayoutCadence.MONTHLY.value}:
            raise ValueError("Payout cadence must be WEEKLY or MONTHLY")
        return key


class CommissionSettingsPublic(BaseModel):
    id: str
    currency: str
    payout_cadence: str
    certificate_rate_percent: Decimal
    claim_rate_percent: Decimal
    enabled: bool
    customer_referral_amount: Decimal
    customer_referrals_enabled: bool
    notes: str | None
    version: int
    updated_at: datetime
    created_at: datetime

    model_config = {"extra": "forbid"}


class CommissionLedgerEntryPublic(BaseModel):
    id: str
    statement_ref: str
    entry_kind: str
    direction: str
    source_event: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    intermediary_id: str | None
    agent_code_snapshot: str | None
    intermediary_name_snapshot: str | None
    base_amount: Decimal | None
    rate_percent_snapshot: Decimal | None
    payment_id: str | None
    policy_id: str | None
    description: str
    occurred_at: datetime
    created_at: datetime

    model_config = {"extra": "forbid"}


class CommissionAccountSummary(BaseModel):
    intermediary_id: str | None
    agent_code: str | None
    name: str
    balance: Decimal
    currency: str
    accrued_total: Decimal
    paid_total: Decimal
    entry_count: int

    model_config = {"extra": "forbid"}


class CommissionStatementPublic(BaseModel):
    account: CommissionAccountSummary
    opening_balance: Decimal
    closing_balance: Decimal
    period_start: datetime | None
    period_end: datetime | None
    entries: list[CommissionLedgerEntryPublic]

    model_config = {"extra": "forbid"}


class CommissionPayoutRequest(BaseModel):
    intermediary_id: str | None = None
    # When true, pay house account (Star Serve retained commissions)
    house: bool = False
    note: str | None = Field(default=None, max_length=500)

    model_config = {"extra": "forbid"}
