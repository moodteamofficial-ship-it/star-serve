"""Product / vehicle reference schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProductCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    cover_options: list[str] = Field(default_factory=list)
    provider_code: str | None = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class ProductPublic(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    cover_options: list[Any]
    is_active: bool
    scope: str  # PLATFORM | TENANT
    provider_code: str | None
    synced_at: datetime | None

    model_config = {"extra": "forbid"}


class VehicleMakePublic(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    sort_order: int
    scope: str
    provider_code: str | None

    model_config = {"extra": "forbid"}


class CancellationReasonPublic(BaseModel):
    id: str
    code: str
    label: str
    is_active: bool
    scope: str

    model_config = {"extra": "forbid"}


class VehicleMakeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    sort_order: int = 0

    model_config = {"extra": "forbid"}
