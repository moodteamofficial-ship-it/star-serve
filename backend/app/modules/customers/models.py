"""Customer domain models — tenant-owned PII, minimize exposure in APIs."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.customers.enums import CustomerOrigin


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        Index(
            "uq_customers_staff_id_number",
            "tenant_id",
            "id_number",
            unique=True,
            postgresql_where=text("origin = 'STAFF'"),
        ),
        Index(
            "uq_customers_guest_session_id_number",
            "tenant_id",
            "guest_session_id",
            "id_number",
            unique=True,
            postgresql_where=text("origin = 'GUEST'"),
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    assigned_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CustomerOrigin.STAFF.value, index=True
    )
    guest_session_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(128))
    id_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kra_pin: Mapped[str | None] = mapped_column(String(16))
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    logbook_url: Mapped[str | None] = mapped_column(String(1024))
    id_front_url: Mapped[str | None] = mapped_column(String(1024))
    id_back_url: Mapped[str | None] = mapped_column(String(1024))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)

    # This person's own shareable code (mirrors customer_referral_codes)
    referral_code: Mapped[str | None] = mapped_column(String(16), index=True)
    # First-touch attribution: the agent QR they scanned, or a customer code they used
    referred_by_intermediary_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "intermediaries.id",
            ondelete="SET NULL",
            name="fk_customers_referred_by_intermediary_id_intermediaries",
        ),
        index=True,
    )
    referred_by_agent_code: Mapped[str | None] = mapped_column(String(16))
    referred_by_agent_name: Mapped[str | None] = mapped_column(String(255))
    referred_by_referral_code: Mapped[str | None] = mapped_column(String(16))
    referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Provider linkage — never trust client to set freely on create
    external_client_ref: Mapped[str | None] = mapped_column(String(128))
    provider_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    last_issuance_job_id: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
