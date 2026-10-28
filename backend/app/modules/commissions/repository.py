"""Commission repositories."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.repository import TenantAwareRepository
from app.core.security.context import SecurityContext
from app.modules.commissions.models import CommissionLedgerEntry, CommissionSettings


class CommissionSettingsRepository(TenantAwareRepository[CommissionSettings]):
    model = CommissionSettings

    async def get_for_tenant(self) -> CommissionSettings | None:
        # Always exact-tenant — never broaden for platform admins (settings are per-agency).
        stmt = (
            select(CommissionSettings)
            .where(CommissionSettings.tenant_id == self.ctx.tenant_id)
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def get_for_update(self) -> CommissionSettings | None:
        stmt = (
            select(CommissionSettings)
            .where(CommissionSettings.tenant_id == self.ctx.tenant_id)
            .with_for_update()
            .limit(1)
        )
        return await self.session.scalar(stmt)


class CommissionLedgerRepository(TenantAwareRepository[CommissionLedgerEntry]):
    model = CommissionLedgerEntry

    def _account_filter(self, stmt: Select, intermediary_id: UUID | None) -> Select:
        if intermediary_id is None:
            return stmt.where(CommissionLedgerEntry.intermediary_id.is_(None))
        return stmt.where(CommissionLedgerEntry.intermediary_id == intermediary_id)

    async def find_by_payment_kind(
        self, payment_id: UUID, entry_kind: str
    ) -> CommissionLedgerEntry | None:
        stmt = (
            self._base_select()
            .where(
                CommissionLedgerEntry.payment_id == payment_id,
                CommissionLedgerEntry.entry_kind == entry_kind,
            )
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def latest_balance(self, intermediary_id: UUID | None) -> Decimal:
        stmt = select(CommissionLedgerEntry.balance_after).where(
            CommissionLedgerEntry.tenant_id == self.ctx.tenant_id
        )
        stmt = self._account_filter(stmt, intermediary_id)
        stmt = stmt.order_by(
            CommissionLedgerEntry.occurred_at.desc(),
            CommissionLedgerEntry.created_at.desc(),
        ).limit(1)
        value = await self.session.scalar(stmt)
        return Decimal(value or 0)

    async def search(
        self,
        *,
        intermediary_id: UUID | None | object = ...,
        house_only: bool = False,
        query: str | None,
        entry_kind: str | None,
        period_start: datetime | None,
        period_end: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[CommissionLedgerEntry], int]:
        stmt = self._base_select()
        count_stmt = select(func.count()).select_from(CommissionLedgerEntry).where(
            CommissionLedgerEntry.tenant_id == self.ctx.tenant_id
        )

        if house_only:
            stmt = stmt.where(CommissionLedgerEntry.intermediary_id.is_(None))
            count_stmt = count_stmt.where(CommissionLedgerEntry.intermediary_id.is_(None))
        elif intermediary_id is not ... and intermediary_id is not None:
            stmt = stmt.where(CommissionLedgerEntry.intermediary_id == intermediary_id)
            count_stmt = count_stmt.where(
                CommissionLedgerEntry.intermediary_id == intermediary_id
            )

        if entry_kind:
            stmt = stmt.where(CommissionLedgerEntry.entry_kind == entry_kind)
            count_stmt = count_stmt.where(CommissionLedgerEntry.entry_kind == entry_kind)
        if period_start:
            stmt = stmt.where(CommissionLedgerEntry.occurred_at >= period_start)
            count_stmt = count_stmt.where(CommissionLedgerEntry.occurred_at >= period_start)
        if period_end:
            stmt = stmt.where(CommissionLedgerEntry.occurred_at <= period_end)
            count_stmt = count_stmt.where(CommissionLedgerEntry.occurred_at <= period_end)
        if query:
            like = f"%{query.strip()}%"
            filt = or_(
                CommissionLedgerEntry.statement_ref.ilike(like),
                CommissionLedgerEntry.description.ilike(like),
                CommissionLedgerEntry.agent_code_snapshot.ilike(like),
                CommissionLedgerEntry.intermediary_name_snapshot.ilike(like),
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)

        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(
            CommissionLedgerEntry.occurred_at.desc(),
            CommissionLedgerEntry.created_at.desc(),
        ).offset(offset).limit(limit)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, total

    async def account_aggregates(self) -> list[dict]:
        """Balances and totals per intermediary (and house)."""
        from app.modules.commissions.enums import CommissionDirection, CommissionEntryKind

        # Latest balance per account via distinct on — portable fallback: group in Python
        stmt = (
            self._base_select()
            .order_by(
                CommissionLedgerEntry.intermediary_id.asc().nullsfirst(),
                CommissionLedgerEntry.occurred_at.desc(),
                CommissionLedgerEntry.created_at.desc(),
            )
        )
        rows = list((await self.session.scalars(stmt)).all())
        latest: dict[str | None, CommissionLedgerEntry] = {}
        accrued: dict[str | None, Decimal] = {}
        paid: dict[str | None, Decimal] = {}
        counts: dict[str | None, int] = {}
        for row in rows:
            key = str(row.intermediary_id) if row.intermediary_id else None
            counts[key] = counts.get(key, 0) + 1
            if key not in latest:
                latest[key] = row
            if row.entry_kind in {
                CommissionEntryKind.ACCRUAL.value,
                CommissionEntryKind.HOUSE.value,
            }:
                accrued[key] = accrued.get(key, Decimal("0")) + Decimal(row.amount)
            if row.entry_kind == CommissionEntryKind.PAYOUT.value:
                paid[key] = paid.get(key, Decimal("0")) + Decimal(row.amount)
            if (
                row.entry_kind == CommissionEntryKind.ADJUSTMENT.value
                and row.direction == CommissionDirection.CREDIT.value
            ):
                accrued[key] = accrued.get(key, Decimal("0")) + Decimal(row.amount)

        out: list[dict] = []
        for key, last in latest.items():
            # Prefer identity from accrual/house rows (payouts may omit snapshots).
            code = last.agent_code_snapshot
            name = last.intermediary_name_snapshot
            if key is not None:
                for row in rows:
                    row_key = str(row.intermediary_id) if row.intermediary_id else None
                    if row_key != key:
                        continue
                    if not code and row.agent_code_snapshot:
                        code = row.agent_code_snapshot
                    if not name and row.intermediary_name_snapshot:
                        name = row.intermediary_name_snapshot
                    if code and name:
                        break
            out.append(
                {
                    "intermediary_id": key,
                    "agent_code": code,
                    "name": name or ("Star Serve" if key is None else "Agent"),
                    "balance": Decimal(last.balance_after),
                    "currency": last.currency,
                    "accrued_total": accrued.get(key, Decimal("0")),
                    "paid_total": paid.get(key, Decimal("0")),
                    "entry_count": counts.get(key, 0),
                }
            )
        out.sort(key=lambda r: (r["intermediary_id"] is not None, r["name"].lower()))
        return out
