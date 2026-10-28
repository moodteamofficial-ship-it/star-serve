"""Insurance orchestration schemas (Star Serve shapes only)."""

from pydantic import BaseModel, Field

from app.core.schemas import AppEmail


class ClientCheckQuery(BaseModel):
    id_number: str = Field(min_length=5, max_length=32)

    model_config = {"extra": "forbid"}


class EnsureClientRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    other_names: str | None = Field(default=None, max_length=128)
    id_number: str = Field(min_length=5, max_length=32)
    kra_pin: str | None = Field(default=None, max_length=16)
    phone: str = Field(min_length=9, max_length=32)
    email: AppEmail | None = None
    create_if_missing: bool = True

    model_config = {"extra": "forbid"}


class EnsureIntermediaryRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: AppEmail
    phone: str = Field(min_length=9, max_length=32)
    identification: str = Field(min_length=5, max_length=64)
    kra_pin: str | None = Field(default=None, max_length=16)
    create_if_missing: bool = True

    model_config = {"extra": "forbid"}


class PremiumCalculateRequest(BaseModel):
    # TPO / PSV often use sumInsured=0 on Definite Assurance
    sum_insured: float = Field(ge=0)
    capacity: float | None = Field(default=None, ge=0)
    tonnage: float | None = Field(default=None, ge=0)
    cover_period: str = Field(min_length=1, max_length=64)
    product: str = Field(min_length=1, max_length=64)
    cover_option: str = Field(min_length=1, max_length=128)
    transaction_type: str = Field(default="1", min_length=1, max_length=64)

    model_config = {"extra": "forbid"}


class PremiumPublic(BaseModel):
    basic_premium: float | None
    phcf: float | None
    training_levy: float | None
    stamp_duty: float | None
    gross_premium: float | None
    cover_period_used: str | None = None

    model_config = {"extra": "ignore"}


class GuestSessionRequest(BaseModel):
    tenant_id: str | None = Field(default=None, max_length=36)

    model_config = {"extra": "forbid"}
