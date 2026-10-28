"""Proposal domain model — tenant-owned insurance workflow record."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.proposals.enums import ProposalStatus


class Proposal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "proposals"

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
    intermediary_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intermediaries.id", ondelete="SET NULL"), index=True
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    product_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cover_option: Mapped[str] = mapped_column(String(128), nullable=False)
    cover_period: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(64), nullable=False, default="NEW")

    vehicle_registration: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    vehicle_make: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_model: Mapped[str | None] = mapped_column(String(128))
    vehicle_year: Mapped[int | None] = mapped_column(Integer)
    chassis_number: Mapped[str | None] = mapped_column(String(64), index=True)
    engine_number: Mapped[str | None] = mapped_column(String(64))
    engine_rating: Mapped[int | None] = mapped_column(Integer)
    make_code: Mapped[str | None] = mapped_column(String(32))
    model_code: Mapped[str | None] = mapped_column(String(32))
    agent_code: Mapped[str | None] = mapped_column(String(64))
    referral_code: Mapped[str | None] = mapped_column(String(16))
    intermediary_name: Mapped[str | None] = mapped_column(String(255))
    ira_number: Mapped[str | None] = mapped_column(String(64))
    sum_insured: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    capacity: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tonnage: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    basic_premium: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    phcf: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    training_levy: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    stamp_duty: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    gross_premium: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProposalStatus.DRAFT.value, index=True
    )
    external_proposal_ref: Mapped[str | None] = mapped_column(String(128))
    provider_note_oid: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_insured_item: Mapped[str | None] = mapped_column(String(64))
    provider_document_number: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_amount_to_pay: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    provider_request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    provider_response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    double_insurance_clear: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    double_insurance_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    policy_check_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    cover_start_date: Mapped[date | None] = mapped_column(Date)
    cover_end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="STAFF", index=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
