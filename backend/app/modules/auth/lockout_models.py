"""ORM model for progressive login lockouts."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LoginLockout(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks failed sign-ins per email + device (and email-global sentinel)."""

    __tablename__ = "login_lockouts"
    __table_args__ = (
        UniqueConstraint("email", "device_fingerprint", name="uq_login_lockouts_email_device"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lockout_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_lock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
