"""USSD persistence — menus, sessions, events, provider settings, admin audit."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UssdMenuConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned menu configuration. Sessions pin to a published version."""

    __tablename__ = "ussd_menu_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_ussd_menu_configs_tenant_version"),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    welcome_text: Mapped[str] = mapped_column(String(320), nullable=False)
    root_screen_key: Mapped[str] = mapped_column(String(64), nullable=False, default="main")
    max_invalid_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    session_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    max_message_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=160)
    nav_back: Mapped[str] = mapped_column(String(8), nullable=False, default="0")
    nav_home: Mapped[str] = mapped_column(String(8), nullable=False, default="00")
    nav_repeat: Mapped[str | None] = mapped_column(String(8))
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)


class UssdProviderSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-tenant provider adapter settings. Secrets are never returned to the browser."""

    __tablename__ = "ussd_provider_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_code", name="uq_ussd_provider_tenant_code"),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    provider_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    service_code: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    callback_path: Mapped[str] = mapped_column(
        String(128), nullable=False, default="/api/v1/ussd/callback"
    )
    auth_header_name: Mapped[str | None] = mapped_column(String(64))
    # Fernet/app-encrypted secret material — never expose raw values via admin API.
    auth_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    allowed_ips: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    protocol_options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))


class UssdSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ussd_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider_session_id", name="uq_ussd_sessions_provider_sid"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    config_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ussd_menu_configs.id"), nullable=False, index=True
    )
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # HMAC of MSISDN — analytics / uniqueness without storing raw numbers in events.
    msisdn_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    msisdn_masked: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    current_screen_key: Mapped[str] = mapped_column(String(64), nullable=False, default="main")
    workflow_action: Mapped[str | None] = mapped_column(String(64))
    workflow_step: Mapped[str | None] = mapped_column(String(64))
    # Collected answers + workflow scratch (no secrets / OTPs).
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    history: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    invalid_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message: Mapped[str | None] = mapped_column(Text)
    last_input: Mapped[str | None] = mapped_column(String(256))
    last_response_type: Mapped[str | None] = mapped_column(String(16))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    guest_session_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    termination_reason: Mapped[str | None] = mapped_column(String(64))


class UssdSessionEvent(Base, UUIDPrimaryKeyMixin):
    """Structured analytics events. Idempotent on (session_id, event_key)."""

    __tablename__ = "ussd_session_events"
    __table_args__ = (
        UniqueConstraint("session_id", "event_key", name="uq_ussd_session_events_key"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ussd_sessions.id"), nullable=False, index=True
    )
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_action: Mapped[str | None] = mapped_column(String(64), index=True)
    step_id: Mapped[str | None] = mapped_column(String(64), index=True)
    screen_key: Mapped[str | None] = mapped_column(String(64))
    config_version: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(32))
    error_category: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    provider_kind: Mapped[str | None] = mapped_column(String(32))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    msisdn_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class UssdIdempotencyRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ussd_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_ussd_idempotency_tenant_key"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    response_type: Mapped[str] = mapped_column(String(16), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UssdAdminAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ussd_admin_audit"

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
