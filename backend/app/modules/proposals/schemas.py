"""Proposal request/response schemas — mass-assignment safe."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProposalCreateRequest(BaseModel):
    customer_id: str
    intermediary_id: str | None = None
    product_code: str = Field(min_length=1, max_length=64)
    cover_option: str = Field(min_length=1, max_length=128)
    cover_period: str = Field(min_length=1, max_length=64)
    transaction_type: str = Field(default="NEW", max_length=64)
    vehicle_registration: str = Field(min_length=3, max_length=32)
    vehicle_make: str = Field(min_length=1, max_length=64)
    vehicle_model: str | None = Field(default=None, max_length=128)
    vehicle_year: int | None = Field(default=None, ge=1980, le=2100)
    sum_insured: Decimal = Field(default=Decimal("0"), ge=0)
    capacity: Decimal | None = Field(default=None, ge=0)
    tonnage: Decimal | None = Field(default=None, ge=0)
    cover_start_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # Explicitly omit premium fields — server calculates via provider

    model_config = {"extra": "forbid"}


class ProposalPublic(BaseModel):
    id: str
    customer_id: str
    intermediary_id: str | None
    product_code: str
    cover_option: str
    cover_period: str
    transaction_type: str
    vehicle_registration: str
    vehicle_make: str
    vehicle_model: str | None
    vehicle_year: int | None
    chassis_number: str | None = None
    engine_number: str | None = None
    engine_rating: int | None = None
    make_code: str | None = None
    model_code: str | None = None
    agent_code: str | None = None
    intermediary_name: str | None = None
    ira_number: str | None = None
    sum_insured: Decimal
    basic_premium: Decimal | None
    phcf: Decimal | None
    training_levy: Decimal | None
    stamp_duty: Decimal | None
    gross_premium: Decimal | None
    status: str
    channel: str = "STAFF"
    double_insurance_clear: bool | None
    external_proposal_ref: str | None
    provider_note_oid: str | None = None
    provider_insured_item: str | None = None
    provider_document_number: str | None = None
    provider_amount_to_pay: Decimal | None = None
    cover_start_date: date | None
    cover_end_date: date | None
    version: int
    job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}


class ProposalRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=512)

    model_config = {"extra": "forbid"}
