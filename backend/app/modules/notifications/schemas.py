"""Notification API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationSendRequest(BaseModel):
    channel: str = Field(max_length=16)
    template_code: str = Field(max_length=64)
    recipient: str = Field(min_length=3, max_length=320)
    context: dict[str, Any] = Field(default_factory=dict)
    customer_id: UUID | None = None
    related_resource: str | None = Field(default=None, max_length=64)
    related_resource_id: UUID | None = None
    deliver_now: bool = True

    model_config = {"extra": "forbid"}


class NotificationPublic(BaseModel):
    id: str
    channel: str
    template_code: str
    recipient: str
    recipient_name: str | None = None
    recipient_avatar_url: str | None = None
    subject: str | None
    body: str
    status: str
    provider: str
    provider_message_id: str | None
    attempt_count: int
    max_attempts: int
    last_error_code: str | None
    last_error_message: str | None
    sent_at: datetime | None
    related_resource: str | None
    related_resource_id: str | None
    customer_id: str | None
    job_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"extra": "forbid"}
