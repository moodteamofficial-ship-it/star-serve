"""Issuance wizard schemas — Definite order: product → client → vehicle → pay → certificate."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schemas import AppEmail


class IssuanceClientRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    other_names: str | None = Field(default=None, max_length=128)
    id_number: str = Field(min_length=5, max_length=32)
    phone: str = Field(min_length=9, max_length=32)
    kra_pin: str | None = Field(default=None, max_length=16)
    # Definite LIVE requires email on the insurer client before generateCertificate.
    email: AppEmail

    model_config = {"extra": "forbid"}


class IssuanceSubmitRequest(BaseModel):
    customer_id: str
    product_external_id: str = Field(min_length=1, max_length=64)
    product_code: str = Field(min_length=1, max_length=64)
    product_name: str | None = Field(default=None, max_length=255)
    cover_option_id: str = Field(min_length=1, max_length=64)
    cover_option_name: str | None = Field(default=None, max_length=128)
    cover_period: str = Field(min_length=1, max_length=64)
    capacity: Decimal = Field(gt=0)
    tonnage: Decimal = Field(default=Decimal("0"), ge=0)
    # TPO / PSV often use sumInsured=0 on Definite Assurance
    sum_insured: Decimal = Field(default=Decimal("0"), ge=0)
    vehicle_registration: str = Field(min_length=3, max_length=32)
    vehicle_make_code: str = Field(min_length=1, max_length=64)
    vehicle_make_name: str = Field(min_length=1, max_length=64)
    vehicle_model_code: str = Field(min_length=1, max_length=64)
    vehicle_model_name: str = Field(min_length=1, max_length=128)
    vehicle_year: int = Field(ge=1980, le=2100)
    chassis_number: str = Field(min_length=3, max_length=64)
    engine_number: str | None = Field(default=None, max_length=64)
    engine_rating: int | None = Field(default=1500, ge=0)
    cover_start_date: date | None = None
    agent_code: str | None = Field(default=None, max_length=64)
    # Selects an approved intermediary owned by the caller's tenant. The name and IRA
    # licence number printed on the certificate are read from that record, never from
    # the request body.
    intermediary_id: str | None = Field(default=None, max_length=64)
    # Period Definite actually priced (e.g. 2installments) — used for newProposal PaymentInterval
    cover_period_used: str | None = Field(default=None, max_length=64)
    # Customer referral code (scanned #r= link); credits the referrer once the cover is paid
    referral_code: str | None = Field(default=None, max_length=16)

    model_config = {"extra": "forbid"}


class IssuancePayCancelRequest(BaseModel):
    policy_id: str

    model_config = {"extra": "forbid"}


class IssuancePayRequest(BaseModel):
    policy_id: str
    method: str = Field(default="MPESA", max_length=32)
    phone: str | None = Field(default=None, max_length=32)

    model_config = {"extra": "forbid"}
