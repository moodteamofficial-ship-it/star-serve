"""Customer request/response schemas — explicit fields only."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AppEmail


class CustomerCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    other_names: str | None = Field(default=None, max_length=128)
    id_number: str = Field(min_length=5, max_length=32)
    kra_pin: str | None = Field(default=None, max_length=16)
    phone: str = Field(min_length=9, max_length=32)
    email: AppEmail | None = None
    date_of_birth: date | None = None
    branch_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}

    @field_validator("first_name", "last_name", "other_names")
    @classmethod
    def strip_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class CustomerUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    other_names: str | None = Field(default=None, max_length=128)
    kra_pin: str | None = Field(default=None, max_length=16)
    phone: str | None = Field(default=None, min_length=9, max_length=32)
    email: AppEmail | None = None
    avatar_url: str | None = Field(default=None, max_length=512)
    date_of_birth: date | None = None
    branch_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # Intentionally omit: tenant_id, id_number, status, external_client_ref, assigned_user_id

    model_config = {"extra": "forbid"}


class CustomerAssignRequest(BaseModel):
    assigned_user_id: str | None = None

    model_config = {"extra": "forbid"}


class CustomerPublic(BaseModel):
    id: str
    first_name: str
    last_name: str
    other_names: str | None
    id_number: str
    kra_pin: str | None
    phone: str
    email: str | None
    avatar_url: str | None = None
    logbook_url: str | None = None
    id_front_url: str | None = None
    id_back_url: str | None = None
    date_of_birth: date | None
    status: str
    branch_id: str | None
    assigned_user_id: str | None
    external_client_ref: str | None
    referral_code: str | None = None
    referred_by_intermediary_id: str | None = None
    referred_by_agent_code: str | None = None
    referred_by_agent_name: str | None = None
    referred_by_referral_code: str | None = None
    referred_at: datetime | None = None
    policies_count: int = 0
    proposals_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
