"""Customer referral codes and credit ledger.

A referral account is a person: (operating agency tenant, national ID). Guest
customers are duplicated per guest session, so the customer row is not stable.

Every read/write here filters by tenant explicitly and runs with a short RLS
bypass, because the code owner and the buyer can sit on different tenant
contexts (platform staff vs the guest agency).
"""

from __future__ import annotations

import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.rls import set_rls_bypass
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.core.validation.identity import normalize_id_number
from app.modules.referrals.models import CustomerReferralCode, CustomerReferralCredit

logger = get_logger(__name__)

MONEY = Decimal("0.01")
CODE_PREFIX = "SS"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_BODY_LENGTH = 6
_CODE_RE = re.compile(rf"^{CODE_PREFIX}[{CODE_ALPHABET}]{{{CODE_BODY_LENGTH}}}$")
# M-Pesa cannot prompt for zero, so the customer always pays at least this much.
MIN_CUSTOMER_CHARGE = Decimal("1")
DEFAULT_REFERRAL_AMOUNT = Decimal("50.00")

ENTRY_EARNED = "EARNED"
ENTRY_REDEEMED = "REDEEMED"
CREDIT = "CREDIT"
DEBIT = "DEBIT"


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def normalize_referral_code(raw: str | None) -> str | None:
    cleaned = re.sub(r"[\s\-]", "", (raw or "")).upper()
    if not cleaned:
        return None
    if not _CODE_RE.match(cleaned):
        return None
    return cleaned


def generate_referral_code() -> str:
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_BODY_LENGTH))
    return f"{CODE_PREFIX}{body}"


def referral_link(code: str) -> str:
    from app.modules.intermediaries.agent_qr import agent_qr_base_url

    return f"{agent_qr_base_url()}/#r={quote(code, safe='')}"


def max_discount(balance: Decimal, gross: Decimal) -> Decimal:
    """Whole shillings only; the customer still pays at least MIN_CUSTOMER_CHARGE."""
    cap = Decimal(gross) - MIN_CUSTOMER_CHARGE
    usable = min(Decimal(balance), cap)
    if usable <= 0:
        return Decimal("0.00")
    return _money(usable.to_integral_value(rounding=ROUND_FLOOR))


@asynccontextmanager
async def rls_bypass(session: AsyncSession) -> AsyncIterator[None]:
    prior = await session.scalar(text("SELECT current_setting('app.rls_bypass', true)"))
    if prior == "true":
        yield
        return
    await set_rls_bypass(session, True)
    try:
        yield
    finally:
        # An aborted transaction rejects the reset; the SET LOCAL dies with it anyway.
        with suppress(Exception):
            await set_rls_bypass(session, False)


async def referral_tenant_id(session: AsyncSession, tenant_id: UUID) -> UUID:
    """Platform-tenant rows belong to the operating (guest) agency, like commissions."""
    from app.modules.insurance.guest_session import resolve_guest_tenant_id
    from app.modules.tenants.models import Tenant

    owner = await session.get(Tenant, tenant_id)
    if owner is not None and bool(owner.is_platform):
        return await resolve_guest_tenant_id(session)
    return tenant_id


@dataclass(frozen=True, slots=True)
class ReferralAccount:
    code: str
    id_number: str
    holder_name: str | None
    phone: str | None
    customer_id: UUID | None
    balance: Decimal
    earned_total: Decimal
    redeemed_total: Decimal
    referrals: int
    created_at: datetime | None


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_code(
        self,
        *,
        tenant_id: UUID,
        id_number: str,
        customer_id: UUID | None = None,
        holder_name: str | None = None,
        phone: str | None = None,
    ) -> CustomerReferralCode:
        tenant = await referral_tenant_id(self.session, tenant_id)
        person = normalize_id_number(id_number)
        async with rls_bypass(self.session):
            existing = await self._code_for_person(tenant, person)
            if existing is not None:
                if customer_id and existing.customer_id is None:
                    existing.customer_id = customer_id
                if holder_name and not existing.holder_name:
                    existing.holder_name = holder_name[:255]
                if phone and not existing.phone:
                    existing.phone = phone[:32]
                await self.session.flush()
                return existing
            for _ in range(8):
                row = CustomerReferralCode(
                    id=uuid4(),
                    tenant_id=tenant,
                    id_number=person,
                    code=generate_referral_code(),
                    customer_id=customer_id,
                    holder_name=(holder_name or "")[:255] or None,
                    phone=(phone or "")[:32] or None,
                )
                try:
                    async with self.session.begin_nested():
                        self.session.add(row)
                        await self.session.flush()
                    return row
                except IntegrityError:
                    raced = await self._code_for_person(tenant, person)
                    if raced is not None:
                        return raced
            raise RuntimeError("Could not allocate a unique referral code")

    async def ensure_code_for_customer(self, customer: Any) -> CustomerReferralCode | None:
        """Best effort: a missing code must never block customer creation or payment."""
        if customer is None or not getattr(customer, "id_number", None):
            return None
        name = " ".join(
            part for part in (customer.first_name, customer.last_name) if part
        ).strip()
        try:
            async with self.session.begin_nested():
                row = await self.ensure_code(
                    tenant_id=customer.tenant_id,
                    id_number=customer.id_number,
                    customer_id=customer.id,
                    holder_name=name or None,
                    phone=customer.phone,
                )
                if getattr(customer, "referral_code", None) != row.code:
                    customer.referral_code = row.code
                # Guest sessions duplicate the person; keep every row on one code.
                async with rls_bypass(self.session):
                    await self.session.execute(
                        text(
                            "UPDATE customers SET referral_code = :code "
                            "WHERE tenant_id = :tenant AND id_number = :person "
                            "AND referral_code IS DISTINCT FROM :code"
                        ),
                        {
                            "code": row.code,
                            "tenant": customer.tenant_id,
                            "person": customer.id_number,
                        },
                    )
                await self.session.flush()
                return row
        except Exception:
            return None

    async def record_attribution(
        self,
        customer: Any,
        *,
        intermediary: Any | None = None,
        referral_code: str | None = None,
    ) -> None:
        """First touch wins: never overwrite who originally brought the customer in."""
        if customer is None:
            return
        already = getattr(customer, "referred_by_intermediary_id", None) or getattr(
            customer, "referred_by_referral_code", None
        )
        if already or (intermediary is None and not referral_code):
            return
        if intermediary is not None:
            customer.referred_by_intermediary_id = intermediary.id
            customer.referred_by_agent_code = (intermediary.agent_code or "")[:16] or None
            customer.referred_by_agent_name = (intermediary.name or "")[:255] or None
        if referral_code:
            customer.referred_by_referral_code = referral_code
        customer.referred_at = datetime.now(UTC)
        await self.session.flush()

    async def _code_for_person(self, tenant: UUID, person: str) -> CustomerReferralCode | None:
        return await self.session.scalar(
            select(CustomerReferralCode).where(
                CustomerReferralCode.tenant_id == tenant,
                CustomerReferralCode.id_number == person,
            )
        )

    async def resolve(self, raw_code: str | None) -> CustomerReferralCode | None:
        code = normalize_referral_code(raw_code)
        if code is None:
            return None
        async with rls_bypass(self.session):
            return await self.session.scalar(
                select(CustomerReferralCode).where(CustomerReferralCode.code == code)
            )

    async def code_for_person(self, tenant_id: UUID, id_number: str) -> CustomerReferralCode | None:
        tenant = await referral_tenant_id(self.session, tenant_id)
        async with rls_bypass(self.session):
            return await self._code_for_person(tenant, normalize_id_number(id_number))

    async def balance(self, tenant_id: UUID, id_number: str) -> Decimal:
        tenant = await referral_tenant_id(self.session, tenant_id)
        async with rls_bypass(self.session):
            return await self._balance(tenant, normalize_id_number(id_number))

    async def _balance(self, tenant: UUID, person: str) -> Decimal:
        signed = case(
            (CustomerReferralCredit.direction == CREDIT, CustomerReferralCredit.amount),
            else_=-CustomerReferralCredit.amount,
        )
        total = await self.session.scalar(
            select(func.coalesce(func.sum(signed), 0)).where(
                CustomerReferralCredit.tenant_id == tenant,
                CustomerReferralCredit.id_number == person,
            )
        )
        return _money(total or 0)

    async def available_discount(
        self, *, tenant_id: UUID, id_number: str, gross: Decimal
    ) -> Decimal:
        return max_discount(await self.balance(tenant_id, id_number), Decimal(gross))

    async def _lock_account(self, tenant: UUID, person: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"referral:{tenant}:{person}"},
        )

    async def _find_payment_entry(
        self, tenant: UUID, payment_id: UUID, entry_kind: str
    ) -> CustomerReferralCredit | None:
        return await self.session.scalar(
            select(CustomerReferralCredit).where(
                CustomerReferralCredit.tenant_id == tenant,
                CustomerReferralCredit.payment_id == payment_id,
                CustomerReferralCredit.entry_kind == entry_kind,
            )
        )

    async def _post(
        self,
        *,
        tenant: UUID,
        person: str,
        code: str,
        entry_kind: str,
        direction: str,
        amount: Decimal,
        description: str,
        payment_id: UUID | None,
        policy_id: UUID | None,
        buyer_customer_id: UUID | None,
        actor_user_id: UUID | None,
        currency: str,
        metadata: dict[str, Any],
        occurred_at: datetime | None,
    ) -> CustomerReferralCredit:
        await self._lock_account(tenant, person)
        prior = await self._balance(tenant, person)
        balance_after = prior + amount if direction == CREDIT else prior - amount
        entry = CustomerReferralCredit(
            id=uuid4(),
            tenant_id=tenant,
            id_number=person,
            referral_code=code,
            entry_kind=entry_kind,
            direction=direction,
            amount=_money(amount),
            balance_after=_money(balance_after),
            currency=currency or "KES",
            payment_id=payment_id,
            policy_id=policy_id,
            buyer_customer_id=buyer_customer_id,
            created_by_user_id=actor_user_id,
            description=description[:500],
            occurred_at=occurred_at or datetime.now(UTC),
            metadata_json=metadata,
        )
        async with self.session.begin_nested():
            self.session.add(entry)
            await self.session.flush()
        return entry

    async def earn_for_payment(
        self,
        *,
        payment: Any,
        policy: Any,
        buyer_id_number: str | None,
        actor_user_id: UUID | None = None,
    ) -> CustomerReferralCredit | None:
        """Credit the referrer once per paid certificate bought with their code."""
        from app.modules.commissions.models import CommissionSettings

        code_row = await self.resolve(getattr(policy, "referral_code", None))
        if code_row is None or not payment.id:
            return None
        if buyer_id_number and normalize_id_number(buyer_id_number) == code_row.id_number:
            return None
        tenant = code_row.tenant_id
        async with rls_bypass(self.session):
            settings = await self.session.scalar(
                select(CommissionSettings).where(CommissionSettings.tenant_id == tenant)
            )
            enabled = True if settings is None else bool(settings.customer_referrals_enabled)
            amount = (
                DEFAULT_REFERRAL_AMOUNT
                if settings is None
                else Decimal(settings.customer_referral_amount or 0)
            )
            if not enabled or amount <= 0:
                return None
            existing = await self._find_payment_entry(tenant, payment.id, ENTRY_EARNED)
            if existing is not None:
                return existing
            try:
                return await self._post(
                    tenant=tenant,
                    person=code_row.id_number,
                    code=code_row.code,
                    entry_kind=ENTRY_EARNED,
                    direction=CREDIT,
                    amount=_money(amount),
                    description=(
                        f"Referral credit — {policy.vehicle_registration or 'vehicle'} "
                        f"cover {policy.policy_number}"
                    ),
                    payment_id=payment.id,
                    policy_id=policy.id,
                    buyer_customer_id=policy.customer_id,
                    actor_user_id=actor_user_id,
                    currency=payment.currency or "KES",
                    metadata={
                        "payment_reference": payment.reference,
                        "policy_number": policy.policy_number,
                    },
                    occurred_at=payment.paid_at,
                )
            except IntegrityError:
                return await self._find_payment_entry(tenant, payment.id, ENTRY_EARNED)

    async def redeem_for_payment(
        self,
        *,
        payment: Any,
        policy: Any,
        buyer_id_number: str,
        actor_user_id: UUID | None = None,
    ) -> CustomerReferralCredit | None:
        """Spend the discount reserved on the payment. Never overdraws the account."""
        discount = _money(getattr(payment, "discount_amount", 0) or 0)
        if discount <= 0 or not payment.id:
            return None
        tenant = await referral_tenant_id(self.session, payment.tenant_id)
        person = normalize_id_number(buyer_id_number)
        async with rls_bypass(self.session):
            existing = await self._find_payment_entry(tenant, payment.id, ENTRY_REDEEMED)
            if existing is not None:
                return existing
            code_row = await self._code_for_person(tenant, person)
            if code_row is None:
                return None
            await self._lock_account(tenant, person)
            available = await self._balance(tenant, person)
            spend = min(discount, available)
            if spend <= 0:
                return None
            try:
                return await self._post(
                    tenant=tenant,
                    person=person,
                    code=code_row.code,
                    entry_kind=ENTRY_REDEEMED,
                    direction=DEBIT,
                    amount=spend,
                    description=f"Referral credit used on cover {policy.policy_number}",
                    payment_id=payment.id,
                    policy_id=policy.id,
                    buyer_customer_id=policy.customer_id,
                    actor_user_id=actor_user_id,
                    currency=payment.currency or "KES",
                    metadata={
                        "payment_reference": payment.reference,
                        "policy_number": policy.policy_number,
                        "discount_reserved": str(discount),
                        "shortfall": str(_money(discount - spend)),
                    },
                    occurred_at=payment.paid_at,
                )
            except IntegrityError:
                return await self._find_payment_entry(tenant, payment.id, ENTRY_REDEEMED)

    async def list_accounts(
        self, *, tenant_id: UUID, query: str | None = None, limit: int = 200
    ) -> list[ReferralAccount]:
        tenant = await referral_tenant_id(self.session, tenant_id)
        credit = CustomerReferralCredit
        earned = func.coalesce(
            func.sum(case((credit.entry_kind == ENTRY_EARNED, credit.amount), else_=0)), 0
        )
        redeemed = func.coalesce(
            func.sum(case((credit.entry_kind == ENTRY_REDEEMED, credit.amount), else_=0)), 0
        )
        signed = func.coalesce(
            func.sum(case((credit.direction == CREDIT, credit.amount), else_=-credit.amount)), 0
        )
        referrals = func.count(case((credit.entry_kind == ENTRY_EARNED, credit.id)))
        stmt = (
            select(CustomerReferralCode, earned, redeemed, signed, referrals)
            .outerjoin(
                credit,
                (credit.tenant_id == CustomerReferralCode.tenant_id)
                & (credit.id_number == CustomerReferralCode.id_number),
            )
            .where(CustomerReferralCode.tenant_id == tenant)
            .group_by(CustomerReferralCode.id)
            .order_by(signed.desc(), CustomerReferralCode.created_at.desc())
            .limit(max(1, min(limit, 500)))
        )
        q = (query or "").strip()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                CustomerReferralCode.code.ilike(like)
                | CustomerReferralCode.id_number.ilike(like)
                | CustomerReferralCode.holder_name.ilike(like)
                | CustomerReferralCode.phone.ilike(like)
            )
        async with rls_bypass(self.session):
            rows = (await self.session.execute(stmt)).all()
        return [
            ReferralAccount(
                code=row[0].code,
                id_number=row[0].id_number,
                holder_name=row[0].holder_name,
                phone=row[0].phone,
                customer_id=row[0].customer_id,
                balance=_money(row[3]),
                earned_total=_money(row[1]),
                redeemed_total=_money(row[2]),
                referrals=int(row[4] or 0),
                created_at=row[0].created_at,
            )
            for row in rows
        ]

    async def list_entries(self, *, tenant_id: UUID, code: str) -> list[CustomerReferralCredit]:
        tenant = await referral_tenant_id(self.session, tenant_id)
        normalized = normalize_referral_code(code)
        if normalized is None:
            return []
        async with rls_bypass(self.session):
            rows = await self.session.scalars(
                select(CustomerReferralCredit)
                .where(
                    CustomerReferralCredit.tenant_id == tenant,
                    CustomerReferralCredit.referral_code == normalized,
                )
                .order_by(CustomerReferralCredit.occurred_at.desc())
                .limit(500)
            )
            return list(rows.all())

    async def kit_channels_for_customer(self, customer: Any) -> list[str]:
        """Enabled notification channels that have a recipient on this customer."""
        return await self._available_kit_channels(customer)

    async def resend_kit_for_customer(
        self,
        *,
        ctx: Any,
        customer: Any,
        channel: str,
    ) -> dict[str, Any]:
        """Queue the referral kit on one enabled channel."""
        code_row = await self.ensure_code_for_customer(customer)
        if code_row is None or not (code_row.code or "").strip():
            raise ValidationAppError("This customer does not have a referral code yet")
        available = await self._available_kit_channels(customer)
        wanted = (channel or "").strip().upper()
        if wanted not in available:
            raise ValidationAppError(
                f"{wanted.title()} is not available for this customer right now"
            )
        queued = await self._notify_referral_kit(
            ctx=ctx,
            customer=customer,
            referral_code=code_row.code,
            channels=[wanted],
            raise_on_failure=True,
        )
        return {
            "channel": wanted,
            "queued": queued,
            "available": available,
            "referral_code": code_row.code,
            "referral_link": referral_link(code_row.code),
        }

    async def _available_kit_channels(self, customer: Any) -> list[str]:
        from app.modules.notifications.enums import NotificationChannel
        from app.modules.system_config.service import SystemConfigService

        cfg = SystemConfigService(self.session)
        email = (getattr(customer, "email", None) or "").strip()
        phone = (getattr(customer, "phone", None) or "").strip()
        candidates: list[tuple[str, bool]] = [
            (NotificationChannel.EMAIL.value, bool(email and "@" in email)),
            (NotificationChannel.SMS.value, bool(phone)),
            (NotificationChannel.WHATSAPP.value, bool(phone)),
        ]
        out: list[str] = []
        for channel, has_recipient in candidates:
            if not has_recipient:
                continue
            try:
                if await cfg.outbound_allowed(channel, live=True):
                    out.append(channel)
            except Exception:
                continue
        return out

    async def _notify_referral_kit(
        self,
        *,
        ctx: Any,
        customer: Any,
        referral_code: str,
        channels: list[str] | None = None,
        raise_on_failure: bool = False,
    ) -> list[str]:
        from app.modules.notifications.enums import NotificationChannel, NotificationTemplate
        from app.modules.notifications.service import NotificationService
        from app.modules.system_config.service import SystemConfigService

        name = " ".join(
            part
            for part in (
                getattr(customer, "first_name", None),
                getattr(customer, "last_name", None),
            )
            if part
        ).strip() or "Customer"
        context = {
            "recipient_name": name,
            "referral_code": referral_code,
            "referral_link": referral_link(referral_code),
            # Reused by the email QR button helper.
            "agent_link": referral_link(referral_code),
        }
        notify = NotificationService(self.session, ctx)
        cfg = SystemConfigService(self.session)
        email = (getattr(customer, "email", None) or "").strip()
        phone = (getattr(customer, "phone", None) or "").strip()
        targets: list[tuple[str, str]] = []
        if email and "@" in email:
            targets.append((NotificationChannel.EMAIL.value, email))
        if phone:
            targets.append((NotificationChannel.SMS.value, phone))
            targets.append((NotificationChannel.WHATSAPP.value, phone))
        allowed = {c.upper() for c in channels} if channels is not None else None
        if allowed is not None:
            targets = [(ch, dest) for ch, dest in targets if ch in allowed]

        queued: list[str] = []
        template = NotificationTemplate.CUSTOMER_REFERRAL_KIT.value
        for channel, recipient in targets:
            try:
                if not await cfg.outbound_allowed(channel, live=True):
                    if raise_on_failure and allowed is not None and channel in allowed:
                        raise ValidationAppError(
                            f"{channel.title()} notifications are switched off"
                        )
                    continue
                async with self.session.begin_nested():
                    result = await notify.enqueue_transactional(
                        channel=channel,
                        template_code=template,
                        recipient=recipient,
                        context=context,
                        related_resource="customer",
                        related_resource_id=getattr(customer, "id", None),
                        customer_id=getattr(customer, "id", None),
                        branch_id=getattr(customer, "branch_id", None),
                    )
                if result is not None:
                    queued.append(channel)
                elif raise_on_failure:
                    raise ValidationAppError(f"Could not queue {channel.title()} for this customer")
            except ValidationAppError:
                if raise_on_failure:
                    raise
                logger.warning(
                    "customer_referral_kit_notify_failed",
                    extra={
                        "customer_id": str(getattr(customer, "id", "")),
                        "channel": channel,
                    },
                    exc_info=True,
                )
            except Exception:
                if raise_on_failure:
                    raise
                logger.warning(
                    "customer_referral_kit_notify_failed",
                    extra={
                        "customer_id": str(getattr(customer, "id", "")),
                        "channel": channel,
                    },
                    exc_info=True,
                )
        return queued
