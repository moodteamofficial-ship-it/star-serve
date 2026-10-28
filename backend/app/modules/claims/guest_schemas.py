"""Guest claim schemas — identity proof only. No tenant, policy, or status IDs."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class GuestClaimCreateRequest(BaseModel):
    policy_number: str = Field(min_length=4, max_length=64)
    vehicle_registration: str = Field(min_length=3, max_length=32)
    id_number: str = Field(min_length=5, max_length=20)
    phone: str = Field(min_length=9, max_length=20)
    incident_date: date
    incident_location: str = Field(min_length=3, max_length=255)
    incident_description: str = Field(min_length=10, max_length=4000)
    police_abstract_number: str | None = Field(default=None, max_length=64)
    driver_name: str | None = Field(default=None, max_length=255)
    claimed_amount: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("100000000"))

    model_config = {"extra": "forbid"}


class GuestClaimLookupRequest(BaseModel):
    claim_number: str = Field(min_length=6, max_length=32)
    id_number: str = Field(min_length=5, max_length=20)
    phone: str = Field(min_length=9, max_length=20)

    model_config = {"extra": "forbid"}


class GuestClaimFollowupRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)

    model_config = {"extra": "forbid"}
