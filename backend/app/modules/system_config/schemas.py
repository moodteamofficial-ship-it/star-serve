"""Pydantic schemas for system configuration."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OperationalState(BaseModel):
    enabled: bool = True
    reason: str | None = None
    disabled_at: datetime | None = None
    disabled_by: str | None = None
    version: int = 1

    model_config = {"extra": "forbid"}


class OperationalUpdateRequest(BaseModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=512)
    expected_version: int = Field(ge=1)

    model_config = {"extra": "forbid"}


class ServicesState(BaseModel):
    services: dict[str, bool]
    version: int = 1

    model_config = {"extra": "forbid"}


class ServicesUpdateRequest(BaseModel):
    services: dict[str, bool]
    reason: str = Field(min_length=3, max_length=512)
    expected_version: int = Field(ge=1)

    model_config = {"extra": "forbid"}


class ChannelState(BaseModel):
    enabled: bool

    model_config = {"extra": "forbid"}


class NotificationChannelsState(BaseModel):
    channels: dict[str, ChannelState]
    version: int = 1

    model_config = {"extra": "forbid"}


class NotificationChannelsUpdateRequest(BaseModel):
    channels: dict[str, ChannelState]
    reason: str = Field(min_length=3, max_length=512)
    expected_version: int = Field(ge=1)

    model_config = {"extra": "forbid"}


class SystemConfigSnapshot(BaseModel):
    operational: OperationalState
    services: ServicesState
    notification_channels: NotificationChannelsState

    model_config = {"extra": "forbid"}


class SettingPublic(BaseModel):
    key: str
    value: dict[str, Any]
    description: str | None = None
    version: int
    updated_by: str | None = None
    updated_at: datetime | None = None

    model_config = {"extra": "forbid"}
