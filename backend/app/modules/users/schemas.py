"""User administration schemas — mass-assignment safe."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AppEmail
from app.core.security.passwords import assert_password_strength


class UserCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: AppEmail
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role_id: UUID
    branch_id: UUID | None = None

    model_config = {"extra": "forbid"}

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("password")
    @classmethod
    def strength(cls, value: str) -> str:
        return assert_password_strength(value)


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: AppEmail | None = None
    phone: str | None = Field(default=None, max_length=32)
    role_id: UUID | None = None
    branch_id: UUID | None = None
    password: str | None = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("password")
    @classmethod
    def strength(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return assert_password_strength(value)


class UserStatusRequest(BaseModel):
    status: str = Field(pattern="^(ACTIVE|DISABLED)$")

    model_config = {"extra": "forbid"}


class UserPublic(BaseModel):
    id: str
    full_name: str
    email: str
    phone: str | None
    status: str
    role_id: str | None
    role_name: str | None = None
    role_code: str | None = None
    branch_id: str | None
    branch_name: str | None = None
    branch_code: str | None = None
    avatar_url: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}


class UserOption(BaseModel):
    id: str
    name: str
    code: str | None = None

    model_config = {"extra": "forbid"}
