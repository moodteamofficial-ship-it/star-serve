"""Tenant-scoped wallet repository."""

from uuid import UUID

from sqlalchemy import func, select

from app.core.database.repository import TenantAwareRepository
from app.core.exceptions import ResourceNotFoundError
from app.modules.wallets.models import Wallet, WalletTransaction


class WalletRepository(TenantAwareRepository[Wallet]):
    model = Wallet

    async def get_or_none(self, *, for_update: bool = False) -> Wallet | None:
        stmt = self._base_select()
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get(self) -> Wallet:
        row = await self.get_or_none()
        if row is None:
            raise ResourceNotFoundError("Wallet not found")
        return row


class WalletTransactionRepository(TenantAwareRepository[WalletTransaction]):
    model = WalletTransaction

    async def list_for_wallet(
        self, wallet_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[WalletTransaction], int]:
        stmt = self._base_select().where(WalletTransaction.wallet_id == wallet_id)
        count_stmt = (
            select(func.count())
            .select_from(WalletTransaction)
            .where(
                WalletTransaction.tenant_id == self.ctx.tenant_id,
                WalletTransaction.wallet_id == wallet_id,
            )
        )
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(stmt)).all()), total
