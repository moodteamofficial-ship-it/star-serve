"""Policy domain model — issued cover after proposal approval/payment."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.policies.enums import PolicyStatus


class Policy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "policy_number", name="uq_policies_tenant_policy_number"),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="SET NULL"), index=True
    )
    intermediary_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intermediaries.id", ondelete="SET NULL"), index=True
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    policy_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    cover_option: Mapped[str] = mapped_column(String(128), nullable=False)
    vehicle_registration: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    vehicle_make: Mapped[str | None] = mapped_column(String(64))
    vehicle_model: Mapped[str | None] = mapped_column(String(128))
    chassis_number: Mapped[str | None] = mapped_column(String(64), index=True)
    engine_number: Mapped[str | None] = mapped_column(String(64))
    engine_rating: Mapped[int | None] = mapped_column(Integer)
    make_code: Mapped[str | None] = mapped_column(String(32))
    model_code: Mapped[str | None] = mapped_column(String(32))
    agent_code: Mapped[str | None] = mapped_column(String(64))
    referral_code: Mapped[str | None] = mapped_column(String(16))
    intermediary_name: Mapped[str | None] = mapped_column(String(255))
    ira_number: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PolicyStatus.PENDING_PAYMENT.value, index=True
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="STAFF", index=True
    )
    gross_premium: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sum_insured: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cover_start_date: Mapped[date | None] = mapped_column(Date)
    cover_end_date: Mapped[date | None] = mapped_column(Date)

    external_policy_ref: Mapped[str | None] = mapped_column(String(128))
    certificate_ref: Mapped[str | None] = mapped_column(String(128))
    provider_note_oid: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_insured_item: Mapped[str | None] = mapped_column(String(64))
    provider_document_number: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_amount_to_pay: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    provider_payment_txn: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_commencement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_expiry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(64))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    provider_payload_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
