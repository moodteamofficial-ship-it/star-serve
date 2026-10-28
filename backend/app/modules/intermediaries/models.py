"""Intermediary / agent models — tenant-owned."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Intermediary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "intermediaries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "identification", name="uq_intermediaries_tenant_identification"
        ),
        UniqueConstraint(
            "tenant_id", "agent_code", name="uq_intermediaries_tenant_agent_code"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    approved_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    # The agent's own login (Sales Agent role); active only while the agent is approved.
    user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    identification: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_code: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    kra_pin: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", index=True
    )
    external_intermediary_ref: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
