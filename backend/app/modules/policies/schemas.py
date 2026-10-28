"""Policy schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PolicyPublic(BaseModel):
    id: str
    customer_id: str
    proposal_id: str | None
    policy_number: str
    product_code: str
    cover_option: str
    vehicle_registration: str
    vehicle_make: str | None
    vehicle_model: str | None
    chassis_number: str | None = None
    engine_number: str | None = None
    engine_rating: int | None = None
    make_code: str | None = None
    model_code: str | None = None
    agent_code: str | None = None
    referral_code: str | None = None
    status: str
    channel: str | None = None
    gross_premium: Decimal | None
    sum_insured: Decimal | None
    cover_start_date: date | None
    cover_end_date: date | None
    external_policy_ref: str | None
    certificate_ref: str | None
    provider_note_oid: str | None = None
    provider_insured_item: str | None = None
    provider_document_number: str | None = None
    provider_amount_to_pay: Decimal | None = None
    provider_payment_txn: str | None = None
    cancellation_reason_code: str | None
    version: int
    job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}


class PolicyCancelRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}
