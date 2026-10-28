"""Tenant wallet and ledger entries."""

from decimal import Decimal
from typing import Any

from sqlalchemy import Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.payments.enums import WalletTxnType


class Wallet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_wallets_tenant"),)

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    ledger_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WalletTransaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "reference", name="uq_wallet_transactions_tenant_reference"
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    wallet_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    payment_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    created_by_user_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True))

    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    txn_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=WalletTxnType.CREDIT.value
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
