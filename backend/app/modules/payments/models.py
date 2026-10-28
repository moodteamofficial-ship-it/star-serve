"""Payment intent / transaction model."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="uq_payments_tenant_reference"),
        Index(
            "uq_payments_one_active_per_policy",
            "policy_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING', 'INITIATED') AND policy_id IS NOT NULL"
            ),
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    policy_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposals.id", ondelete="SET NULL"), index=True
    )
    initiated_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )

    reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PaymentPurpose.POLICY_PREMIUM.value
    )
    method: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PaymentMethod.MPESA.value
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    # Authoritative amount from policy/premium — never from client
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Referral credit taken off the premium; amount + discount_amount = gross premium
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PaymentStatus.INITIATED.value, index=True
    )

    phone: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="MPESA")
    provider_checkout_id: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_receipt: Mapped[str | None] = mapped_column(String(128))
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), index=True)
