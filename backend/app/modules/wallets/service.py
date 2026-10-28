"""Wallet ledger — credits and debits with row locking."""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.payments.enums import WalletTxnType
from app.modules.wallets.models import Wallet, WalletTransaction
from app.modules.wallets.repository import WalletRepository, WalletTransactionRepository


def wallet_to_public(row: Wallet) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "currency": row.currency,
        "available_balance": row.available_balance,
        "ledger_balance": row.ledger_balance,
        "status": row.status,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def txn_to_public(row: WalletTransaction) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "reference": row.reference,
        "txn_type": row.txn_type,
        "amount": row.amount,
        "balance_after": row.balance_after,
        "description": row.description,
        "payment_id": str(row.payment_id) if row.payment_id else None,
        "created_at": row.created_at,
    }


class WalletService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self.repo = WalletRepository(session, ctx)
        self.txns = WalletTransactionRepository(session, ctx)
        self.audit = AuditService(session)

    async def get_or_create(self, *, currency: str = "KES") -> Wallet:
        self.ctx.require_active_tenant()
        existing = await self.repo.get_or_none()
        if existing:
            return existing
        wallet = Wallet(
            tenant_id=self.ctx.tenant_id,
            currency=currency,
            available_balance=Decimal("0.00"),
            ledger_balance=Decimal("0.00"),
            status="ACTIVE",
        )
        await self.repo.add(wallet)
        await self.session.flush()
        await self.audit.record(
            action="wallet.create",
            resource="wallet",
            resource_id=str(wallet.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
        )
        return wallet

    async def list_transactions(
        self, *, page: int, limit: int
    ) -> tuple[Wallet, list[WalletTransaction], int]:
        self.ctx.require_staff_principal()
        wallet = await self.get_or_create()
        rows, total = await self.txns.list_for_wallet(
            wallet.id, offset=(page - 1) * limit, limit=limit
        )
        return wallet, rows, total

    async def credit(
        self,
        *,
        amount: Decimal,
        reference: str,
        description: str | None = None,
        payment_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WalletTransaction:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        if amount <= 0:
            raise ValidationAppError("Credit amount must be positive")
        await self.get_or_create()
        wallet = await self.repo.get_or_none(for_update=True) or await self.get_or_create()
        if wallet.status != "ACTIVE":
            raise ValidationAppError("Wallet is not active")
        wallet.available_balance = Decimal(wallet.available_balance) + amount
        wallet.ledger_balance = Decimal(wallet.ledger_balance) + amount
        wallet.version += 1
        txn = WalletTransaction(
            tenant_id=self.ctx.tenant_id,
            wallet_id=wallet.id,
            payment_id=payment_id,
            created_by_user_id=self.ctx.user_id,
            reference=reference,
            txn_type=WalletTxnType.CREDIT.value,
            amount=amount,
            balance_after=wallet.available_balance,
            description=description,
            metadata_json=metadata or {},
        )
        await self.txns.add(txn)
        await self.session.flush()
        await self.audit.record(
            action="wallet.credit",
            resource="wallet",
            resource_id=str(wallet.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"amount": str(amount), "reference": reference},
        )
        return txn

    async def debit(
        self,
        *,
        amount: Decimal,
        reference: str,
        description: str | None = None,
        payment_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WalletTransaction:
        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        if amount <= 0:
            raise ValidationAppError("Debit amount must be positive")
        await self.get_or_create()
        wallet = await self.repo.get_or_none(for_update=True) or await self.get_or_create()
        if wallet.status != "ACTIVE":
            raise ValidationAppError("Wallet is not active")
        available = Decimal(wallet.available_balance)
        if available < amount:
            raise ValidationAppError("Insufficient wallet balance")
        wallet.available_balance = available - amount
        wallet.ledger_balance = Decimal(wallet.ledger_balance) - amount
        wallet.version += 1
        txn = WalletTransaction(
            tenant_id=self.ctx.tenant_id,
            wallet_id=wallet.id,
            payment_id=payment_id,
            created_by_user_id=self.ctx.user_id,
            reference=reference,
            txn_type=WalletTxnType.DEBIT.value,
            amount=amount,
            balance_after=wallet.available_balance,
            description=description,
            metadata_json=metadata or {},
        )
        await self.txns.add(txn)
        await self.session.flush()
        await self.audit.record(
            action="wallet.debit",
            resource="wallet",
            resource_id=str(wallet.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"amount": str(amount), "reference": reference},
        )
        return txn

    async def top_up(self, *, amount: Decimal, description: str | None) -> Wallet:
        """Manual/admin credit — disabled in production unless explicitly allowed."""
        self.ctx.require_staff_principal()
        if not get_settings().manual_wallet_credit_allowed:
            raise ValidationAppError("Manual wallet credit is disabled in this environment")
        reason = (description or "").strip()
        if len(reason) < 8:
            raise ValidationAppError("A reason of at least 8 characters is required for wallet top-up")
        ref = f"TOPUP-{uuid4().hex[:12].upper()}"
        await self.credit(amount=amount, reference=ref, description=reason)
        return await self.get_or_create()
