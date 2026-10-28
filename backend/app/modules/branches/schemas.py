"""Branch administration schemas — mass-assignment safe."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AppEmail


class BranchCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    email: AppEmail | None = None
    city: str | None = Field(default=None, max_length=128)
    address_line: str | None = Field(default=None, max_length=512)

    model_config = {"extra": "forbid"}

    @field_validator("name", "code", "city", "address_line")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class BranchUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    email: AppEmail | None = None
    city: str | None = Field(default=None, max_length=128)
    address_line: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")

    model_config = {"extra": "forbid"}

    @field_validator("name", "code", "city", "address_line")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class BranchPublic(BaseModel):
    id: str
    name: str
    code: str | None
    status: str
    phone: str | None
    email: str | None
    city: str | None
    address_line: str | None
    users_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
