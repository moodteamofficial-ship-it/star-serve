"""Outbound notification records — delivery status is authoritative."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.notifications.enums import NotificationChannel, NotificationStatus


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_notifications_tenant_idempotency"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    related_resource: Mapped[str | None] = mapped_column(String(64))
    related_resource_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)

    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default=NotificationChannel.SMS.value, index=True
    )
    template_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(
        "context", JSONB, nullable=False, default=dict
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=NotificationStatus.QUEUED.value, index=True
    )
    # Lower sends first (OTP 10 … bulk 100). Worker ORDER BY uses this.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="STUB")
    provider_message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
