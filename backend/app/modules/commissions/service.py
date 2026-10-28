"""Commission settings, accrual on payment success, and bank-style statements."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.core.security.context import SecurityContext
from app.modules.audit.service import AuditService
from app.modules.commissions.enums import (
    CommissionDirection,
    CommissionEntryKind,
    CommissionSourceEvent,
    PayoutCadence,
)
from app.modules.commissions.models import CommissionLedgerEntry, CommissionSettings
from app.modules.commissions.repository import (
    CommissionLedgerRepository,
    CommissionSettingsRepository,
)
from app.modules.commissions.schemas import CommissionSettingsUpdateRequest
from app.modules.intermediaries.models import Intermediary
from app.modules.intermediaries.repository import IntermediaryRepository
from app.modules.payments.models import Payment
from app.modules.policies.models import Policy


MONEY = Decimal("0.01")
HOUSE_NAME = "Star Serve"


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def settings_public(row: CommissionSettings) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "currency": row.currency,
        "payout_cadence": row.payout_cadence,
        "certificate_rate_percent": row.certificate_rate_percent,
        "claim_rate_percent": row.claim_rate_percent,
        "enabled": row.enabled,
        "customer_referral_amount": row.customer_referral_amount,
        "customer_referrals_enabled": row.customer_referrals_enabled,
        "notes": row.notes,
        "version": row.version,
        "updated_at": row.updated_at,
        "created_at": row.created_at,
    }


def entry_public(row: CommissionLedgerEntry) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "statement_ref": row.statement_ref,
        "entry_kind": row.entry_kind,
        "direction": row.direction,
        "source_event": row.source_event,
        "amount": row.amount,
        "balance_after": row.balance_after,
        "currency": row.currency,
        "intermediary_id": str(row.intermediary_id) if row.intermediary_id else None,
        "agent_code_snapshot": row.agent_code_snapshot,
        "intermediary_name_snapshot": row.intermediary_name_snapshot,
        "base_amount": row.base_amount,
        "rate_percent_snapshot": row.rate_percent_snapshot,
        "payment_id": str(row.payment_id) if row.payment_id else None,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "description": row.description,
        "occurred_at": row.occurred_at,
        "created_at": row.created_at,
    }


class CommissionService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx
        self._settings_repo: CommissionSettingsRepository | None = None
        self._ledger: CommissionLedgerRepository | None = None
        self.audit = AuditService(session)
        self._ops_ready = False

    async def _ensure_ops(self) -> SecurityContext:
        """Bind settings/ledger to the guest agency when staff are on platform."""
        from app.core.security.ops_tenant import with_ops_context

        if not self._ops_ready:
            self.ctx = await with_ops_context(self.session, self.ctx)
            self._settings_repo = CommissionSettingsRepository(self.session, self.ctx)
            self._ledger = CommissionLedgerRepository(self.session, self.ctx)
            self._ops_ready = True
        return self.ctx

    @property
    def settings_repo(self) -> CommissionSettingsRepository:
        if self._settings_repo is None:
            self._settings_repo = CommissionSettingsRepository(self.session, self.ctx)
        return self._settings_repo

    @property
    def ledger(self) -> CommissionLedgerRepository:
        if self._ledger is None:
            self._ledger = CommissionLedgerRepository(self.session, self.ctx)
        return self._ledger

    async def get_or_create_settings(self) -> CommissionSettings:
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        row = await self.settings_repo.get_for_tenant()
        if row is not None:
            return row
        row = CommissionSettings(
            id=uuid4(),
            tenant_id=self.ctx.tenant_id,
            currency="KES",
            payout_cadence=PayoutCadence.MONTHLY.value,
            certificate_rate_percent=Decimal("0.0000"),
            claim_rate_percent=Decimal("0.0000"),
            enabled=True,
            customer_referral_amount=Decimal("50.00"),
            customer_referrals_enabled=True,
            version=1,
        )
        await self.settings_repo.add(row)
        await self.session.flush()
        return row

    async def update_settings(self, body: CommissionSettingsUpdateRequest) -> CommissionSettings:
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        row = await self.settings_repo.get_for_update()
        if row is None:
            row = await self.get_or_create_settings()
            row = await self.settings_repo.get_for_update() or row
        previous = settings_public(row)
        row.certificate_rate_percent = _money(body.certificate_rate_percent)
        row.claim_rate_percent = _money(body.claim_rate_percent)
        row.payout_cadence = body.payout_cadence
        row.enabled = body.enabled
        if body.customer_referral_amount is not None:
            row.customer_referral_amount = _money(body.customer_referral_amount)
        if body.customer_referrals_enabled is not None:
            row.customer_referrals_enabled = body.customer_referrals_enabled
        row.notes = (body.notes or "").strip() or None
        row.currency = body.currency.strip().upper() or "KES"
        row.updated_by_user_id = self.ctx.actor_user_id
        row.version = int(row.version or 1) + 1
        await self.session.flush()
        await self.audit.record(
            action="commission.settings_update",
            resource="commission_settings",
            resource_id=str(row.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"previous": previous, "next": settings_public(row)},
        )
        return row

    async def _next_statement_ref(self) -> str:
        # Time-ordered unique ref; collision retry handled by unique constraint.
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"COM-{stamp}-{uuid4().hex[:6].upper()}"

    async def _post_entry(
        self,
        *,
        intermediary_id: UUID | None,
        entry_kind: str,
        direction: str,
        source_event: str,
        amount: Decimal,
        currency: str,
        description: str,
        agent_code: str | None,
        intermediary_name: str | None,
        base_amount: Decimal | None = None,
        rate_percent: Decimal | None = None,
        settings_version: int | None = None,
        payment_id: UUID | None = None,
        policy_id: UUID | None = None,
        proposal_id: UUID | None = None,
        certificate_id: UUID | None = None,
        claim_id: UUID | None = None,
        payout_batch_id: UUID | None = None,
        branch_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> CommissionLedgerEntry:
        amount = _money(amount)
        if amount <= 0:
            raise ValidationAppError("Commission amount must be greater than zero")

        prior = await self.ledger.latest_balance(intermediary_id)
        if direction == CommissionDirection.CREDIT.value:
            balance_after = _money(prior + amount)
        else:
            balance_after = _money(prior - amount)

        entry = CommissionLedgerEntry(
            id=uuid4(),
            tenant_id=self.ctx.tenant_id,
            branch_id=branch_id,
            intermediary_id=intermediary_id,
            created_by_user_id=self.ctx.actor_user_id,
            statement_ref=await self._next_statement_ref(),
            entry_kind=entry_kind,
            direction=direction,
            source_event=source_event,
            amount=amount,
            balance_after=balance_after,
            currency=currency,
            agent_code_snapshot=agent_code,
            intermediary_name_snapshot=intermediary_name or (
                HOUSE_NAME if intermediary_id is None else None
            ),
            base_amount=base_amount,
            rate_percent_snapshot=rate_percent,
            settings_version=settings_version,
            payment_id=payment_id,
            policy_id=policy_id,
            proposal_id=proposal_id,
            certificate_id=certificate_id,
            claim_id=claim_id,
            payout_batch_id=payout_batch_id,
            description=description[:500],
            occurred_at=occurred_at or datetime.now(UTC),
            metadata_json=metadata or {},
        )
        await self.ledger.add(entry)
        await self.session.flush()
        return entry

    async def accrue_for_successful_payment(
        self, payment: Payment, policy: Policy
    ) -> CommissionLedgerEntry | None:
        """Idempotent accrual after payment SUCCESS.

        With an approved agent on the policy → agent ACCRUAL.
        Without → HOUSE retention for Star Serve (still ledgered).
        """
        # Accrue against the payment's tenant (guest agency), not the caller's home.
        if payment.tenant_id and payment.tenant_id != self.ctx.tenant_id:
            from dataclasses import replace

            self.ctx = replace(self.ctx, tenant_id=payment.tenant_id)
            self._settings_repo = CommissionSettingsRepository(self.session, self.ctx)
            self._ledger = CommissionLedgerRepository(self.session, self.ctx)
            self._ops_ready = True
        else:
            await self._ensure_ops()

        self.ctx.require_active_tenant()
        if not payment.id:
            return None

        settings = await self.get_or_create_settings()
        if not settings.enabled:
            return None

        rate = Decimal(settings.certificate_rate_percent or 0)
        paid = Decimal(payment.amount or 0) + Decimal(getattr(payment, "discount_amount", 0) or 0)
        base = paid or Decimal(policy.gross_premium or 0)
        if base <= 0 or rate < 0:
            return None
        commission = _money(base * rate / Decimal("100"))
        if commission <= 0:
            return None

        agent: Intermediary | None = None
        if policy.intermediary_id:
            try:
                agent = await IntermediaryRepository(self.session, self.ctx).get_active_by_id(
                    policy.intermediary_id
                )
            except Exception:
                agent = None
            if agent and str(agent.status).upper() != "APPROVED":
                agent = None

        is_house = agent is None
        entry_kind = (
            CommissionEntryKind.HOUSE.value if is_house else CommissionEntryKind.ACCRUAL.value
        )
        existing = await self.ledger.find_by_payment_kind(payment.id, entry_kind)
        if existing is not None:
            return existing

        agent_code = (agent.agent_code if agent else None) or None
        agent_name = (agent.name if agent else None) or policy.intermediary_name
        description = (
            f"House retention on paid certificate {policy.policy_number}"
            if is_house
            else f"Commission on paid certificate {policy.policy_number}"
        )

        try:
            async with self.session.begin_nested():
                entry = await self._post_entry(
                    intermediary_id=None if is_house else agent.id,
                    entry_kind=entry_kind,
                    direction=CommissionDirection.CREDIT.value,
                    source_event=CommissionSourceEvent.CERTIFICATE_PAYMENT.value,
                    amount=commission,
                    currency=payment.currency or settings.currency or "KES",
                    description=description,
                    agent_code=agent_code,
                    intermediary_name=agent_name if not is_house else HOUSE_NAME,
                    base_amount=_money(base),
                    rate_percent=rate,
                    settings_version=settings.version,
                    payment_id=payment.id,
                    policy_id=policy.id,
                    proposal_id=policy.proposal_id if getattr(policy, "proposal_id", None) else None,
                    branch_id=getattr(policy, "branch_id", None) or payment.branch_id,
                    metadata={
                        "payment_reference": payment.reference,
                        "policy_number": policy.policy_number,
                        "vehicle_registration": policy.vehicle_registration,
                        "beneficiary": "HOUSE" if is_house else "AGENT",
                    },
                    occurred_at=payment.paid_at or datetime.now(UTC),
                )
        except IntegrityError:
            return await self.ledger.find_by_payment_kind(payment.id, entry_kind)

        await self.audit.record(
            action="commission.accrue",
            resource="commission_ledger",
            resource_id=str(entry.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "statement_ref": entry.statement_ref,
                "entry_kind": entry.entry_kind,
                "amount": str(entry.amount),
                "payment_id": str(payment.id),
                "policy_id": str(policy.id),
                "intermediary_id": str(entry.intermediary_id) if entry.intermediary_id else None,
                "beneficiary": "HOUSE" if is_house else "AGENT",
            },
        )
        return entry

    async def list_accounts(self) -> list[dict[str, Any]]:
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        return await self.ledger.account_aggregates()

    async def list_entries(
        self,
        *,
        page: int,
        limit: int,
        intermediary_id: UUID | None = None,
        house_only: bool = False,
        query: str | None = None,
        entry_kind: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> tuple[list[CommissionLedgerEntry], int]:
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        return await self.ledger.search(
            intermediary_id=intermediary_id if intermediary_id is not None else ...,
            house_only=house_only,
            query=query,
            entry_kind=entry_kind,
            period_start=period_start,
            period_end=period_end,
            offset=(page - 1) * limit,
            limit=limit,
        )

    async def statement(
        self,
        *,
        intermediary_id: UUID | None,
        house: bool = False,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        if house:
            intermediary_id = None
            house_only = True
        else:
            house_only = intermediary_id is None and house
        rows, _ = await self.ledger.search(
            intermediary_id=intermediary_id if not house_only else ...,
            house_only=house_only or (intermediary_id is None and house),
            query=None,
            entry_kind=None,
            period_start=period_start,
            period_end=period_end,
            offset=0,
            limit=limit,
        )
        # Chronological for statement
        chronological = list(reversed(rows))
        opening = Decimal("0.00")
        if chronological:
            first = chronological[0]
            if first.direction == CommissionDirection.CREDIT.value:
                opening = _money(Decimal(first.balance_after) - Decimal(first.amount))
            else:
                opening = _money(Decimal(first.balance_after) + Decimal(first.amount))
        closing = (
            Decimal(chronological[-1].balance_after) if chronological else await self.ledger.latest_balance(
                None if house or intermediary_id is None else intermediary_id
            )
        )
        name = HOUSE_NAME
        agent_code = None
        if intermediary_id and not house:
            try:
                agent = await IntermediaryRepository(self.session, self.ctx).get_active_by_id(
                    intermediary_id
                )
                name = agent.name
                agent_code = agent.agent_code
            except Exception:
                if chronological:
                    name = chronological[0].intermediary_name_snapshot or name
                    agent_code = chronological[0].agent_code_snapshot
        elif chronological:
            name = chronological[0].intermediary_name_snapshot or HOUSE_NAME
            agent_code = chronological[0].agent_code_snapshot

        accrued = sum(
            (Decimal(r.amount) for r in chronological if r.entry_kind in {"ACCRUAL", "HOUSE"}),
            Decimal("0"),
        )
        paid = sum(
            (Decimal(r.amount) for r in chronological if r.entry_kind == "PAYOUT"),
            Decimal("0"),
        )
        return {
            "account": {
                "intermediary_id": str(intermediary_id) if intermediary_id and not house else None,
                "agent_code": agent_code,
                "name": name,
                "balance": _money(closing),
                "currency": chronological[0].currency if chronological else "KES",
                "accrued_total": _money(accrued),
                "paid_total": _money(paid),
                "entry_count": len(chronological),
            },
            "opening_balance": _money(opening),
            "closing_balance": _money(closing),
            "period_start": period_start,
            "period_end": period_end,
            "entries": [entry_public(r) for r in chronological],
        }

    async def record_payout(
        self,
        *,
        intermediary_id: UUID | None,
        house: bool = False,
        note: str | None = None,
    ) -> CommissionLedgerEntry:
        """Pay out the full outstanding balance for an agent (or house) account."""
        await self._ensure_ops()
        self.ctx.require_active_tenant()
        account_id = None if house else intermediary_id
        balance = await self.ledger.latest_balance(account_id)
        if balance <= 0:
            raise ValidationAppError("No outstanding commission balance to pay")

        agent_code = None
        name = HOUSE_NAME
        if account_id:
            agent = await IntermediaryRepository(self.session, self.ctx).get_active_by_id(account_id)
            agent_code = agent.agent_code
            name = agent.name

        batch_id = uuid4()
        settings = await self.get_or_create_settings()
        entry = await self._post_entry(
            intermediary_id=account_id,
            entry_kind=CommissionEntryKind.PAYOUT.value,
            direction=CommissionDirection.DEBIT.value,
            source_event=CommissionSourceEvent.PAYOUT.value,
            amount=balance,
            currency=settings.currency,
            description=(note or "").strip() or f"Commission payout — {name}",
            agent_code=agent_code,
            intermediary_name=name,
            payout_batch_id=batch_id,
            metadata={"payout_batch_id": str(batch_id), "cadence": settings.payout_cadence},
        )
        await self.audit.record(
            action="commission.payout",
            resource="commission_ledger",
            resource_id=str(entry.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "statement_ref": entry.statement_ref,
                "amount": str(entry.amount),
                "intermediary_id": str(account_id) if account_id else None,
                "payout_batch_id": str(batch_id),
            },
        )
        return entry
