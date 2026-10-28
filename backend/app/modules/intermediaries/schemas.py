"""Intermediary schemas — mass-assignment safe."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import AppEmail


def _normalize_optional_agent_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.strip()
    if not code:
        return None
    if not code.isdigit() or len(code) != 6:
        raise ValueError("Agent code must be exactly 6 digits")
    return code


class IntermediaryCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: AppEmail
    phone: str = Field(min_length=9, max_length=32)
    identification: str = Field(min_length=5, max_length=64)
    agent_code: str | None = Field(default=None, max_length=6)
    kra_pin: str | None = Field(default=None, max_length=16)
    branch_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # Sign-in password for the agent's Sales Agent login (works once approved).
    password: str | None = Field(default=None, min_length=6, max_length=128)

    model_config = {"extra": "forbid"}

    @field_validator("agent_code", mode="before")
    @classmethod
    def validate_agent_code(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_optional_agent_code(str(value))


class IntermediaryLoginRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)

    model_config = {"extra": "forbid"}


class IntermediaryResendKitRequest(BaseModel):
    channel: Literal["EMAIL", "SMS", "WHATSAPP"]

    model_config = {"extra": "forbid"}


class GuestAgentApplicationRequest(BaseModel):
    """Public self-registration. Status, tenant, and branch are server-assigned."""

    name: str = Field(min_length=2, max_length=255)
    email: AppEmail
    phone: str = Field(min_length=9, max_length=32)
    identification: str = Field(min_length=5, max_length=64)
    agent_code: str | None = Field(default=None, max_length=6)
    kra_pin: str | None = Field(default=None, max_length=16)
    # Sales Agent login password; the login stays pending until an admin approves.
    password: str | None = Field(default=None, min_length=6, max_length=128)
    # Honeypot: hidden in the form, so any value means an automated submit.
    website: str | None = Field(default=None, max_length=255)

    model_config = {"extra": "forbid"}

    @field_validator("agent_code", mode="before")
    @classmethod
    def validate_agent_code(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_optional_agent_code(str(value))


class IntermediaryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: AppEmail | None = None
    phone: str | None = Field(default=None, min_length=9, max_length=32)
    kra_pin: str | None = Field(default=None, max_length=16)
    branch_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    # Omit: tenant_id, identification, agent_code, status, external refs, approved_*

    model_config = {"extra": "forbid"}


class IntermediaryPublic(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    identification: str
    agent_code: str
    kra_pin: str | None
    status: str
    branch_id: str | None
    external_intermediary_ref: str | None
    approved_at: datetime | None
    has_login: bool = False
    login_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
