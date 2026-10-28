"""User and session models — soft-delete only (never hard DELETE)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database.enums import SessionStatus, UserStatus

# Register FK targets on metadata (countries / currencies / branches)
import app.modules.reference.models  # noqa: F401
import app.modules.tenants.models  # noqa: F401


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    # Unique (tenant_id, email) for active rows only — see partial index in migration 0009

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Primary role — used for sign-in authorization; must also exist in user_roles
    role_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # Home / default branch (also mirrored in user_branches for multi-branch)
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64))
    # ISO 3166-1 alpha-2 (e.g. KE) and dialing prefix (e.g. +254)
    country_code: Mapped[str | None] = mapped_column(String(8), index=True)
    phone_country_code: Mapped[str | None] = mapped_column(String(8))
    country_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("countries.id", ondelete="SET NULL"),
        index=True,
    )
    currency: Mapped[str] = mapped_column(
        String(8),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
        default="KES",
        index=True,
    )
    gender: Mapped[str | None] = mapped_column(String(32))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    timezone: Mapped[str | None] = mapped_column(String(64))
    locale: Mapped[str | None] = mapped_column(String(16))
    avatar_url: Mapped[str | None] = mapped_column(String(512))

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # OTP challenge — hash only; never expose via API / UserPublic
    otp_hash: Mapped[str | None] = mapped_column(String(128))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_channel: Mapped[str | None] = mapped_column(String(16))  # sms | email | whatsapp

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UserStatus.PENDING.value, index=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Target data plane for this user — updated on env switch; never routes DB inside one process.
    preferred_app_env: Mapped[str] = mapped_column(
        String(32), nullable=False, default="development"
    )


class UserBranch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_branches"

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class UserTeam(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_teams"

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    team_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


class Session(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sessions"

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Snapshot of users.role_id at issue time — must still match on every request
    role_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    app_env: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SessionStatus.ACTIVE.value, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    family_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_label: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
