"""Auth request/response schemas — explicit fields only (mass-assignment safe)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AppEmail
from app.core.security.passwords import assert_password_strength

AppEnvLiteral = Literal["development", "staging", "production", "backup"]


class LoginRequest(BaseModel):
    email: AppEmail
    password: str = Field(min_length=8, max_length=128)

    model_config = {"extra": "forbid"}


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)

    model_config = {"extra": "forbid"}

    @field_validator("new_password")
    @classmethod
    def strength(cls, value: str) -> str:
        return assert_password_strength(value)


class PreferredAppEnvRequest(BaseModel):
    """User's target data plane — stored server-side; frontend syncs localStorage to match."""

    app_env: AppEnvLiteral

    model_config = {"extra": "forbid"}


class UserPublic(BaseModel):
    """Shell-safe profile — no precise location; phone is masked."""

    id: str
    email: AppEmail
    full_name: str
    phone: str | None = None  # masked, e.g. ***1234
    tenant_id: str
    role_id: str
    role_code: str
    branch_id: str | None = None
    country_code: str | None = None
    phone_country_code: str | None = None
    country_id: str | None = None
    currency: str = "KES"
    timezone: str | None = None
    locale: str | None = None
    avatar_url: str | None = None
    permissions: list[str] = []
    # API deployment this session is bound to (must match server APP_ENV)
    app_env: str = "development"
    # User's chosen target — drives frontend API host selection after login
    preferred_app_env: str = "development"

    model_config = {"extra": "forbid"}


class LoginData(BaseModel):
    user: UserPublic
    expires_in: int

    model_config = {"extra": "forbid"}
