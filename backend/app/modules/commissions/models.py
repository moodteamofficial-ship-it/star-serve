"""Commission settings and bank-style ledger models."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.commissions.enums import (
    CommissionDirection,
    CommissionEntryKind,
    CommissionSourceEvent,
    PayoutCadence,
)


class CommissionSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tenant commission plan — rates and payout cadence."""

    __tablename__ = "commission_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_commission_settings_tenant"),)

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    updated_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    payout_cadence: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PayoutCadence.MONTHLY.value
    )
    # Percent of paid premium (gross) — e.g. 10.00 = 10%
    certificate_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0.0000")
    )
    claim_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0.0000")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Flat credit (not a percent) earned by a customer whose code is used on a paid cover
    customer_referral_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("50.00")
    )
    customer_referrals_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CommissionLedgerEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable-style commission ledger line (statement row)."""

    __tablename__ = "commission_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "statement_ref",
            name="uq_commission_ledger_tenant_statement_ref",
        ),
        UniqueConstraint(
            "tenant_id",
            "payment_id",
            "entry_kind",
            name="uq_commission_ledger_payment_kind",
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    branch_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    # NULL = Star Serve house account (no agent attributed)
    intermediary_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))

    statement_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entry_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CommissionEntryKind.ACCRUAL.value, index=True
    )
    direction: Mapped[str] = mapped_column(
        String(8), nullable=False, default=CommissionDirection.CREDIT.value
    )
    source_event: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CommissionSourceEvent.CERTIFICATE_PAYMENT.value
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")

    # Snapshots for audit / statements (never rely on live joins alone)
    agent_code_snapshot: Mapped[str | None] = mapped_column(String(16))
    intermediary_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rate_percent_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    settings_version: Mapped[int | None] = mapped_column(Integer)

    payment_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    policy_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    proposal_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    certificate_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    claim_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    payout_batch_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)

    description: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
