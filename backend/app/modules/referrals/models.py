"""Customer referral codes and the referral credit ledger."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CustomerReferralCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One shareable code per person (tenant + national ID)."""

    __tablename__ = "customer_referral_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id_number", name="uq_customer_referral_codes_person"),
        UniqueConstraint("code", name="uq_customer_referral_codes_code"),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    id_number: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    customer_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    holder_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))


class CustomerReferralCredit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Credit ledger line. Credits are spent as premium discounts, never paid out."""

    __tablename__ = "customer_referral_credits"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "payment_id", "entry_kind", name="uq_customer_referral_credits_payment"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False)
    id_number: Mapped[str] = mapped_column(String(32), nullable=False)
    referral_code: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    payment_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    policy_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    buyer_customer_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
