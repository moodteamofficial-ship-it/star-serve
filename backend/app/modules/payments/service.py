"""Payment service — authoritative amounts, webhook-driven success only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import set_rls_context
from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import AuthenticationError, ResourceNotFoundError, ValidationAppError
from app.core.idempotency.service import IdempotencyService
from app.core.security.context import SecurityContext
from app.integrations.insurance.ports import InsuranceProvider
from app.integrations.payments.factory import get_payment_provider
from app.modules.audit.service import AuditService
from app.modules.certificates.service import CertificateService
from app.modules.jobs.models import IdempotencyKey
from app.modules.jobs.service import JobService
from app.modules.payments.enums import (
    ASYNC_STK_METHODS,
    USER_CANCELLED_PAYMENT,
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
)
from app.modules.payments.models import Payment
from app.modules.payments.repository import (
    PaymentRepository,
    find_payment_by_checkout_global,
    find_payment_by_reference_global,
)
from app.modules.payments.webhook_bind import (
    IDENTITY_CHECKOUT,
    assert_policy_accepts_settlement,
    assert_webhook_bound_to_payment,
    authenticated_payment_lookup,
    may_apply_failure,
    may_apply_success,
)
from app.modules.payments.schemas import PaymentInitiateRequest
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.repository import PolicyRepository
from app.modules.wallets.service import WalletService


TERMINAL_STATUSES = {
    PaymentStatus.SUCCESS.value,
    PaymentStatus.FAILED.value,
    PaymentStatus.REVERSED.value,
    PaymentStatus.CANCELLED.value,
}

# Callback URLs and their HMAC tokens authenticate the callback, so they are
# credentials: keep them out of the stored payload (and out of anything derived
# from it, such as support exports or job event payloads).
_REDACTED_PAYLOAD_KEYS = frozenset(
    {"callbackurl", "callback_url", "sig", "signature", "token", "authorization"}
)


def _redact_provider_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    return {
        key: ("[redacted]" if str(key).lower() in _REDACTED_PAYLOAD_KEYS else value)
        for key, value in raw.items()
    }


_FAILURE_REASONS_BY_CODE = {
    "1": "insufficient M-Pesa balance",
    "1001": "another M-Pesa transaction was in progress",
    "1019": "the M-Pesa request expired",
    "1032": "the M-Pesa request was cancelled",
    "1037": "the M-Pesa prompt timed out",
    "2001": "an incorrect M-Pesa PIN was entered",
}
_FAILURE_REASON_KEYWORDS = (
    ("insufficient", "insufficient M-Pesa balance"),
    ("balance", "insufficient M-Pesa balance"),
    ("cancel", "the M-Pesa request was cancelled"),
    ("timeout", "the M-Pesa prompt timed out"),
    ("timed out", "the M-Pesa prompt timed out"),
    ("unreachable", "the phone could not be reached"),
    ("pin", "an incorrect M-Pesa PIN was entered"),
    ("expired", "the M-Pesa request expired"),
)


def friendly_failure_reason(code: str | None, message: str | None) -> str:
    """Customer-safe reason; raw provider text never reaches the SMS."""
    normalized = (code or "").strip()
    if normalized in _FAILURE_REASONS_BY_CODE:
        return _FAILURE_REASONS_BY_CODE[normalized]
    haystack = f"{normalized} {message or ''}".lower()
    for needle, reason in _FAILURE_REASON_KEYWORDS:
        if needle in haystack:
            return reason
    return "the payment could not be completed"


def _payment_message_context(payment: Payment, policy: Any, customer: Any) -> dict[str, str]:
    try:
        amount = f"{Decimal(payment.amount):,.2f}"
    except Exception:
        amount = str(payment.amount)
    return {
        "recipient_name": (getattr(customer, "first_name", "") or "").strip().title(),
        "reference": payment.reference,
        "amount": amount,
        "currency": payment.currency or "KES",
        "policy_number": getattr(policy, "policy_number", "") or "",
        "vehicle_registration": getattr(policy, "vehicle_registration", "") or "",
    }


def to_public(row: Payment, *, attribution: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "id": str(row.id),
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "proposal_id": str(row.proposal_id) if row.proposal_id else None,
        "reference": row.reference,
        "purpose": row.purpose,
        "method": row.method,
        "currency": row.currency,
        "amount": str(row.amount) if row.amount is not None else None,
        "discount_amount": str(getattr(row, "discount_amount", None) or 0),
        "status": row.status,
        "phone": row.phone,
        "provider": row.provider,
        "provider_receipt": row.provider_receipt,
        "failure_code": row.failure_code,
        "failure_message": row.failure_message,
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "version": row.version,
        "job_id": row.job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "intermediary_id": None,
        "intermediary_name": None,
        "agent_code": None,
        "commission_beneficiary": None,
    }
    if attribution:
        data.update(attribution)
    return data


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.insurance = provider
        self.repo = PaymentRepository(session, ctx)
        self.policies = PolicyRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)
        self.idempotency = IdempotencyService(session)
        self.wallets = WalletService(session, ctx)
        self.certificates = CertificateService(session, ctx, provider)

    async def list(
        self, *, page: int, limit: int, query: str | None, status: str | None
    ) -> tuple[list[Payment], int]:
        self.ctx.require_staff_principal()
        return await self.repo.search(
            query=query, status=status, offset=(page - 1) * limit, limit=limit
        )

    async def attribution_for_payments(
        self, rows: list[Payment]
    ) -> dict[UUID, dict[str, Any]]:
        """Map payment id → agent attribution for list/detail responses."""
        from sqlalchemy import select

        from app.modules.commissions.enums import CommissionEntryKind
        from app.modules.commissions.models import CommissionLedgerEntry
        from app.modules.intermediaries.models import Intermediary
        from app.modules.policies.models import Policy

        out: dict[UUID, dict[str, Any]] = {}
        if not rows:
            return out

        policy_ids = [r.policy_id for r in rows if r.policy_id]
        by_policy: dict[Any, Policy] = {}
        agents: dict[Any, Intermediary] = {}
        if policy_ids:
            # Do not bind to the staff home tenant — guest payments/policies live on
            # the ops agency while platform admins authenticate to the platform tenant.
            policy_stmt = select(Policy).where(Policy.id.in_(policy_ids))
            if not self.ctx.is_platform_admin:
                allowed_tenants = {self.ctx.tenant_id}
                for pay in rows:
                    if getattr(pay, "tenant_id", None):
                        allowed_tenants.add(pay.tenant_id)
                policy_stmt = policy_stmt.where(Policy.tenant_id.in_(allowed_tenants))

            policies = list((await self.session.scalars(policy_stmt)).all())
            by_policy = {p.id: p for p in policies}
            agent_ids = [p.intermediary_id for p in policies if p.intermediary_id]
            if agent_ids:
                agent_stmt = select(Intermediary).where(
                    Intermediary.id.in_(agent_ids),
                    Intermediary.deleted_at.is_(None),
                )
                if not self.ctx.is_platform_admin:
                    agent_stmt = agent_stmt.where(
                        Intermediary.tenant_id.in_({p.tenant_id for p in policies})
                    )
                for row in (await self.session.scalars(agent_stmt)).all():
                    agents[row.id] = row

        for pay in rows:
            if not pay.policy_id or pay.policy_id not in by_policy:
                out[pay.id] = {
                    "intermediary_id": None,
                    "intermediary_name": None,
                    "agent_code": None,
                    "commission_beneficiary": "HOUSE",
                }
                continue
            policy = by_policy[pay.policy_id]
            agent = agents.get(policy.intermediary_id) if policy.intermediary_id else None
            if agent and str(agent.status).upper() == "APPROVED":
                out[pay.id] = {
                    "intermediary_id": str(agent.id),
                    "intermediary_name": agent.name,
                    "agent_code": agent.agent_code,
                    "commission_beneficiary": "AGENT",
                }
            elif policy.intermediary_id and (policy.intermediary_name or "").strip():
                # FK present but agent row not visible / not approved — still show name.
                out[pay.id] = {
                    "intermediary_id": str(policy.intermediary_id),
                    "intermediary_name": policy.intermediary_name,
                    "agent_code": None,
                    "commission_beneficiary": "AGENT",
                }
            else:
                out[pay.id] = {
                    "intermediary_id": None,
                    "intermediary_name": None,
                    "agent_code": None,
                    "commission_beneficiary": "HOUSE",
                }

        # Prefer commission ledger ACCRUAL rows when present (source of truth after pay).
        payment_ids = [pay.id for pay in rows if pay.id]
        if payment_ids:
            ledger_stmt = select(CommissionLedgerEntry).where(
                CommissionLedgerEntry.payment_id.in_(payment_ids),
                CommissionLedgerEntry.entry_kind == CommissionEntryKind.ACCRUAL.value,
                CommissionLedgerEntry.intermediary_id.is_not(None),
            )
            for entry in (await self.session.scalars(ledger_stmt)).all():
                if not entry.payment_id:
                    continue
                out[entry.payment_id] = {
                    "intermediary_id": str(entry.intermediary_id),
                    "intermediary_name": entry.intermediary_name_snapshot,
                    "agent_code": entry.agent_code_snapshot,
                    "commission_beneficiary": "AGENT",
                }
        return out

    async def get(self, payment_id: UUID) -> Payment:
        payment = await self.repo.get(payment_id)
        return await self.sync_definite_stk_confirmation(payment)

    async def initiate(
        self,
        body: PaymentInitiateRequest,
        *,
        idempotency_key: str | None,
        generate_certificate: bool = True,
    ) -> Payment | dict[str, Any]:
        """Settle premium locally.

        Issuance rails (see ``settlement.py``):
        - DEFINITE_WALLET: one Definite ``initiatePayment`` (method 3) debits agency
          float during the call, so it settles to SUCCESS here. Needs ``wallet:debit``.
        - DEFINITE_MPESA: Definite (method 1) waits for the customer STK. Local
          payment stays PENDING until Definite replies that the note is approved
          (no StarServe webhook — Safaricom callbacks Definite, not us).
        - BIRDVIEW: local STK PENDING until webhook; Definite wallet settle happens at cert

        When ``generate_certificate`` is False (issuance wizard), certificate issuance
        is owned by ``IssuanceService.pay`` so Definite cannot fire twice in one request.
        """
        self.ctx.require_active_tenant()
        from app.modules.insurance.definite_settlement import DefiniteSettlementService
        from app.modules.payments.settlement import GUEST_ALLOWED_RAILS, resolve_settlement_plan
        from app.modules.system_config.service import SystemConfigService

        await SystemConfigService(self.session).require_service("payments")

        plan = resolve_settlement_plan(body.method)
        method = plan.rail.value
        if self.ctx.is_guest and method not in GUEST_ALLOWED_RAILS:
            raise ValidationAppError("Guest payments must use BirdView M-Pesa")
        if plan.required_permission:
            self.ctx.require_permission(plan.required_permission)
        if plan.requires_phone and not (body.phone or "").strip():
            raise ValidationAppError(f"{plan.label} requires a phone number for the STK prompt")

        payload = {
            "policy_id": str(body.policy_id),
            "method": method,
            "phone": body.phone,
        }
        idem_record: IdempotencyKey | None = None
        if idempotency_key:
            started = await self.idempotency.begin(
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                key=idempotency_key,
                operation="payment.initiate",
                request_hash=IdempotencyService.hash_request(payload),
            )
            if isinstance(started, dict):
                return started
            idem_record = started

        payment, created, job = await self.get_or_create_payment_attempt(
            body,
            method=method,
            idempotency_key=idempotency_key,
        )
        if not created:
            public = to_public(payment)
            if idem_record is not None:
                await self.idempotency.complete(
                    idem_record, response_body=public, job_id=payment.job_id
                )
            return payment
        policy = await self.policies.get(payment.policy_id)
        amount = Decimal(payment.amount).quantize(Decimal("0.01"))
        reference = payment.reference

        pay_provider = get_payment_provider(method)
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message=f"initiate:{method}")
        await self.jobs.transition(job, JobStatus.WAITING_PAYMENT)

        # Definite rails settle the insurer note once here (wallet=3 / M-Pesa STK=1).
        # BirdView settles Definite wallet later on the certificate path.
        definite_receipt: str | None = None
        definite_confirmed = False
        if not plan.local_async_stk:
            try:
                settled = await DefiniteSettlementService(
                    self.session, self.ctx, self.insurance
                ).approve_note_once(
                    policy,
                    definite_payment_method=plan.definite_payment_method,
                    phone=body.phone,
                    receipt=reference[:20],
                    job=job,
                )
                definite_receipt = str(settled.get("receipt") or reference)
                definite_confirmed = bool(settled.get("confirmed"))
            except Exception as exc:
                payment.status = PaymentStatus.FAILED.value
                payment.failure_code = "DEFINITE_SETTLE_FAILED"
                payment.failure_message = (
                    str(exc)[:240]
                    if isinstance(exc, ValidationAppError)
                    else "Definite settlement failed"
                )
                payment.version += 1
                await self.session.flush()
                await self.jobs.transition(
                    job, JobStatus.FAILED, error_code="DEFINITE_SETTLE_FAILED"
                )
                raise

        try:
            result = await pay_provider.initiate(
                reference=reference,
                amount=amount,
                currency="KES",
                phone=body.phone,
                metadata={
                    "policy_id": str(policy.id),
                    "policy_number": policy.policy_number,
                    "settlement_rail": method,
                    "definite_receipt": definite_receipt,
                },
            )
        except Exception as exc:
            payment.status = PaymentStatus.FAILED.value
            payment.failure_code = "PROVIDER_INIT_FAILED"
            payment.failure_message = (
                str(exc)[:240]
                if isinstance(exc, ValidationAppError)
                else "Payment provider initiation failed"
            )
            payment.version += 1
            await self.session.flush()
            await self.jobs.transition(
                job, JobStatus.WAITING_EXTERNAL_SERVICE, error_code="PROVIDER_INIT_FAILED"
            )
            raise

        payment.provider_checkout_id = result.provider_checkout_id
        payment.provider_payload = _redact_provider_payload(result.raw)
        payment.provider_receipt = result.receipt or definite_receipt
        # A provider adapter may never settle a customer-funded rail: an accepted
        # STK request is not a payment. Only float-funded rails, or a Definite
        # reply that the note is already approved, move money inline.
        if definite_confirmed:
            result.status = "SUCCESS"
        elif result.status == "SUCCESS" and not plan.settles_on_initiate:
            result.status = "PENDING"
        if result.status == "SUCCESS":
            payment.status = PaymentStatus.SUCCESS.value
            payment.paid_at = datetime.now(UTC)
            payment.version += 1
            await self.session.flush()
            await self._on_success(
                payment,
                policy_id=policy.id,
                generate_certificate=generate_certificate,
            )
            await self.jobs.transition(job, JobStatus.COMPLETED)
        else:
            payment.status = PaymentStatus.PENDING.value
            payment.version += 1
            await self.session.flush()
            # Stay WAITING_PAYMENT until Definite confirms (MPESA) or BirdView webhook

        await self.audit.record(
            action="payment.initiate",
            resource="payment",
            resource_id=str(payment.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "reference": reference,
                "method": method,
                "amount": str(amount),
                "status": payment.status,
            },
        )
        public = to_public(payment)
        if idem_record is not None:
            await self.idempotency.complete(
                idem_record, response_body=public, job_id=payment.job_id
            )
        return payment

    async def get_or_create_payment_attempt(
        self,
        body: PaymentInitiateRequest,
        *,
        method: str,
        idempotency_key: str | None,
    ) -> tuple[Payment, bool, Any]:
        """At most one active (PENDING/INITIATED) payment may settle a policy."""
        policy = await self.policies.get_for_update(body.policy_id)
        self.ctx.assert_branch_access(getattr(policy, "branch_id", None))
        if policy.status != PolicyStatus.PENDING_PAYMENT.value:
            raise ValidationAppError("Policy is not awaiting payment")
        if policy.gross_premium is None or Decimal(policy.gross_premium) <= 0:
            raise ValidationAppError("Policy missing authoritative premium")

        existing = await self.repo.find_active_attempt_for_policy(policy.id)
        if existing is not None:
            if self._expire_stale_stk_attempt(existing):
                await self.session.flush()
            else:
                return existing, False, None

        gross = Decimal(policy.gross_premium).quantize(Decimal("0.01"))
        from app.modules.insurance.fees import monthly_referral_cost, resolve_cover_period

        # BirdView collects cash for Star Serve: monthly cover adds a fixed referral
        # cost on top of Definite's total. Definite is settled later at ``gross`` only.
        # Definite wallet/M-Pesa rails cannot skim an agency fee, so they charge gross.
        referral_cost = Decimal("0.00")
        discount = Decimal("0.00")
        if method == PaymentMethod.BIRDVIEW.value:
            referral_cost = monthly_referral_cost(
                await resolve_cover_period(self.session, self.ctx, policy)
            )
            discount = await self._referral_discount(
                policy, (gross + referral_cost).quantize(Decimal("0.01"))
            )
        amount = (gross + referral_cost - discount).quantize(Decimal("0.01"))
        reference = f"PAY-{uuid4().hex[:12].upper()}"
        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.PAYMENT_INITIATION,
        )
        payment = Payment(
            tenant_id=self.ctx.tenant_id,
            customer_id=policy.customer_id,
            policy_id=policy.id,
            proposal_id=policy.proposal_id,
            branch_id=getattr(policy, "branch_id", None),
            initiated_by_user_id=self.ctx.actor_user_id,
            reference=reference,
            purpose=PaymentPurpose.POLICY_PREMIUM.value,
            method=method,
            currency="KES",
            amount=amount,
            discount_amount=discount,
            status=PaymentStatus.INITIATED.value,
            phone=body.phone,
            provider=method,
            idempotency_key=idempotency_key,
            job_id=job.job_key,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(payment)
                await self.session.flush()
        except IntegrityError:
            raced = await self.repo.find_active_attempt_for_policy(policy.id)
            if raced is not None:
                return raced, False, None
            raise
        return payment, True, job

    async def _referral_discount(self, policy: Any, gross: Decimal) -> Decimal:
        from app.modules.customers.repository import CustomerRepository
        from app.modules.referrals.service import ReferralService

        if policy.customer_id is None:
            return Decimal("0.00")
        try:
            async with self.session.begin_nested():
                customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                    policy.customer_id
                )
                return await ReferralService(self.session).available_discount(
                    tenant_id=customer.tenant_id,
                    id_number=customer.id_number,
                    gross=gross,
                )
        except Exception:
            await self.audit.record(
                action="referral.discount_unavailable",
                resource="policy",
                resource_id=str(policy.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                result="FAILURE",
            )
            return Decimal("0.00")

    async def _settle_referrals(self, payment: Payment, policy: Any) -> None:
        """Spend the buyer's reserved discount and credit whoever referred them."""
        from app.modules.customers.repository import CustomerRepository
        from app.modules.referrals.service import ReferralService

        service = ReferralService(self.session)
        buyer_id_number: str | None = None
        try:
            async with self.session.begin_nested():
                if policy.customer_id is not None:
                    buyer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                        policy.customer_id
                    )
                    buyer_id_number = buyer.id_number
                    await service.ensure_code_for_customer(buyer)
                    await service.redeem_for_payment(
                        payment=payment,
                        policy=policy,
                        buyer_id_number=buyer.id_number,
                        actor_user_id=self.ctx.actor_user_id,
                    )
                await service.earn_for_payment(
                    payment=payment,
                    policy=policy,
                    buyer_id_number=buyer_id_number,
                    actor_user_id=self.ctx.actor_user_id,
                )
        except Exception:
            await self.audit.record(
                action="referral.settle_deferred",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                result="FAILURE",
                metadata={"policy_id": str(policy.id)},
            )

    # Unsigned cancel/timeout cannot mark FAILED. After this window the STK is
    # dead and the unique slot must be released so a new prompt can be sent.
    STK_RETRY_AFTER = timedelta(minutes=3)

    def _expire_stale_stk_attempt(self, payment: Payment) -> bool:
        if payment.method not in ASYNC_STK_METHODS:
            return False
        if payment.status not in {
            PaymentStatus.PENDING.value,
            PaymentStatus.INITIATED.value,
        }:
            return False
        started = payment.created_at
        if started is None:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if datetime.now(UTC) - started < self.STK_RETRY_AFTER:
            return False
        payment.status = PaymentStatus.FAILED.value
        payment.failure_code = "STK_EXPIRED"
        payment.failure_message = "STK prompt expired — a new payment can be started"
        payment.version = int(payment.version or 1) + 1
        return True

    async def _on_success(
        self,
        payment: Payment,
        *,
        policy_id: UUID,
        generate_certificate: bool = True,
    ) -> None:
        """Activate policy after verified SUCCESS; optionally ask Definite for the cert."""
        policy = await self.policies.get(policy_id)
        if policy.status == PolicyStatus.PENDING_PAYMENT.value:
            policy.status = PolicyStatus.PENDING_CERTIFICATE.value
            policy.version += 1
            await self.session.flush()
        # Activate via status transition used by PolicyService
        if policy.status == PolicyStatus.PENDING_CERTIFICATE.value:
            policy.status = PolicyStatus.ACTIVE.value
            policy.version += 1
            await self.session.flush()
        await self.audit.record(
            action="policy.activate_via_payment",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"payment_id": str(payment.id), "reference": payment.reference},
        )
        try:
            from app.modules.commissions.service import CommissionService

            await CommissionService(self.session, self.ctx).accrue_for_successful_payment(
                payment, policy
            )
        except Exception:
            await self.audit.record(
                action="commission.accrue_deferred",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                result="FAILURE",
                metadata={"policy_id": str(policy.id)},
            )
        await self._settle_referrals(payment, policy)
        if generate_certificate:
            try:
                await self.certificates.generate_for_policy(policy.id, payment_id=payment.id)
            except Exception:
                # Payment succeeded; certificate can be retried — do not reverse payment
                await self.audit.record(
                    action="certificate.generate_deferred",
                    resource="policy",
                    resource_id=str(policy.id),
                    tenant_id=self.ctx.tenant_id,
                    user_id=self.ctx.actor_user_id,
                    result="FAILURE",
                    metadata={"payment_id": str(payment.id)},
                )
        await self._notify_payment_success(payment, policy)

    async def _referral_message_context(self, customer: Any) -> dict[str, str]:
        from sqlalchemy import select

        from app.modules.commissions.models import CommissionSettings
        from app.modules.referrals.service import (
            ReferralService,
            referral_link,
            referral_tenant_id,
            rls_bypass,
        )

        try:
            async with self.session.begin_nested():
                service = ReferralService(self.session)
                code = await service.ensure_code_for_customer(customer)
                if code is None:
                    return {}
                balance = await service.balance(customer.tenant_id, customer.id_number)
                tenant = await referral_tenant_id(self.session, customer.tenant_id)
                async with rls_bypass(self.session):
                    settings = await self.session.scalar(
                        select(CommissionSettings).where(CommissionSettings.tenant_id == tenant)
                    )
        except Exception:
            return {}
        if settings is not None and not settings.customer_referrals_enabled:
            return {}
        reward = Decimal(settings.customer_referral_amount if settings else 50)
        reward_text = f"KES {reward:,.0f}"
        shs_text = f"shs {reward:,.0f}"
        link = referral_link(code.code)
        out = {
            "referral_code": code.code,
            "referral_link": link,
            "referral_promo": f"REFER A FRIEND AND EARN {shs_text}",
            "referral_offer": (
                f"Earn {reward_text} off your next cover for every friend who buys with your code"
            ),
            "referral_note": (
                f"REFER A FRIEND AND EARN {shs_text}. Share this link: {link}"
            ),
        }
        if balance > 0:
            out["referral_credit"] = f"KES {balance:,.2f} available on your next cover"
        return out

    async def _notify_payment_success(self, payment: Payment, policy: Any) -> None:
        """Best-effort customer notifications — never fail the payment path."""
        from app.modules.customers.repository import CustomerRepository
        from app.modules.notifications.enums import NotificationChannel, NotificationTemplate
        from app.modules.notifications.service import NotificationService
        from app.modules.policies.models import Policy

        if not isinstance(policy, Policy):
            return
        try:
            customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                policy.customer_id
            )
        except Exception:
            return

        notify = NotificationService(self.session, self.ctx)
        ctx = {
            **_payment_message_context(payment, policy, customer),
            "receipt": payment.provider_receipt or "",
            "cover_start_date": str(policy.cover_start_date or ""),
            "cover_end_date": str(policy.cover_end_date or ""),
            **await self._referral_message_context(customer),
        }
        if customer.phone:
            await self._enqueue_customer_notice(
                notify,
                payment,
                channel=NotificationChannel.SMS.value,
                template_code=NotificationTemplate.PAYMENT_RECEIVED.value,
                recipient=customer.phone,
                context=ctx,
                related_resource="payment",
                related_resource_id=payment.id,
                customer_id=customer.id,
            )
        if customer.email:
            await self._enqueue_customer_notice(
                notify,
                payment,
                channel=NotificationChannel.EMAIL.value,
                template_code=NotificationTemplate.POLICY_ACTIVATED.value,
                recipient=customer.email,
                context=ctx,
                related_resource="policy",
                related_resource_id=policy.id,
                customer_id=customer.id,
            )

    async def _notify_payment_failed(self, payment: Payment) -> None:
        """Best-effort SMS when the rail reports a verified failure."""
        from app.modules.customers.repository import CustomerRepository
        from app.modules.notifications.enums import NotificationChannel, NotificationTemplate
        from app.modules.notifications.service import NotificationService

        if payment.policy_id is None:
            return
        try:
            policy = await self.policies.get(payment.policy_id)
            customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                policy.customer_id
            )
        except Exception:
            return
        if not customer.phone:
            return
        await self._enqueue_customer_notice(
            NotificationService(self.session, self.ctx),
            payment,
            channel=NotificationChannel.SMS.value,
            template_code=NotificationTemplate.PAYMENT_FAILED.value,
            recipient=customer.phone,
            context={
                **_payment_message_context(payment, policy, customer),
                "failure_reason": friendly_failure_reason(
                    payment.failure_code, payment.failure_message
                ),
            },
            related_resource="payment",
            related_resource_id=payment.id,
            customer_id=customer.id,
        )

    async def _enqueue_customer_notice(
        self, notify: Any, payment: Payment, **kwargs: Any
    ) -> None:
        """One channel at a time — a switched-off channel must not block the others."""
        try:
            async with self.session.begin_nested():
                await notify.enqueue_system(**kwargs)
        except Exception:
            await self.audit.record(
                action="notification.enqueue_deferred",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                result="FAILURE",
                metadata={
                    "channel": kwargs.get("channel"),
                    "template": kwargs.get("template_code"),
                },
            )

    async def apply_webhook(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        method: str = PaymentMethod.MPESA.value,
    ) -> Payment:
        """Verify signature, match amount, transition state — never trust client success."""
        pay_provider = get_payment_provider(method)
        verified = await pay_provider.verify_webhook(headers=headers, payload=payload)
        if not verified.valid:
            raise ValidationAppError("Webhook verification failed")

        identity_kind, identity_value = authenticated_payment_lookup(verified)
        await set_rls_context(self.session, tenant_id=None, rls_bypass=True)
        if identity_kind == IDENTITY_CHECKOUT:
            payment = await find_payment_by_checkout_global(self.session, identity_value)
        else:
            payment = await find_payment_by_reference_global(self.session, identity_value)
        if payment is None:
            raise ResourceNotFoundError("Payment not found for checkout id")

        await set_rls_context(
            self.session, tenant_id=payment.tenant_id, is_platform_admin=False
        )
        # Rebind context to payment tenant for subsequent ops
        self.ctx.tenant_id = payment.tenant_id
        self.repo = PaymentRepository(self.session, self.ctx)
        self.policies = PolicyRepository(self.session, self.ctx)
        self.wallets = WalletService(self.session, self.ctx)
        self.certificates = CertificateService(self.session, self.ctx, self.insurance)

        assert_webhook_bound_to_payment(payment, verified, method=method)

        # The customer may still approve a prompt they abandoned in the wizard;
        # money was taken, so that success must settle the policy.
        late_success_after_user_cancel = (
            verified.success
            and payment.status == PaymentStatus.CANCELLED.value
            and payment.failure_code == USER_CANCELLED_PAYMENT
        )

        if payment.status in TERMINAL_STATUSES and not late_success_after_user_cancel:
            # Idempotent replay
            return payment

        if not late_success_after_user_cancel and payment.status not in {
            PaymentStatus.PENDING.value,
            PaymentStatus.INITIATED.value,
        }:
            raise ValidationAppError("Payment cannot accept webhook in current state")

        if not verified.success and not may_apply_failure(verified):
            payment.provider_payload = {
                **(payment.provider_payload or {}),
                "unsigned_failure": _redact_provider_payload(verified.raw),
            }
            await self.session.flush()
            await self.audit.record(
                action="payment.unsigned_failure_ignored",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=payment.tenant_id,
                result="FAILURE",
                metadata={"code": verified.failure_code},
            )
            return payment

        if verified.success:
            if not may_apply_success(verified):
                raise AuthenticationError("Unsigned success requires the stored checkout id")
            if payment.policy_id:
                policy = await self.policies.get_for_update(payment.policy_id)
                winner = await self.repo.find_success_for_policy(payment.policy_id)
                if winner is not None and winner.id != payment.id:
                    payment.status = PaymentStatus.FAILED.value
                    payment.failure_code = "SUPERSEDED"
                    payment.failure_message = "Another payment already settled this policy"
                    payment.version += 1
                    await self.session.flush()
                    await self.audit.record(
                        action="payment.webhook_superseded",
                        resource="payment",
                        resource_id=str(payment.id),
                        tenant_id=payment.tenant_id,
                        result="FAILURE",
                        metadata={"winner_id": str(winner.id)},
                    )
                    return payment
                assert_policy_accepts_settlement(
                    policy, payment_tenant_id=payment.tenant_id
                )

        if verified.success and verified.amount is None:
            raise ValidationAppError("Webhook missing amount")
        if verified.amount is not None:
            received = Decimal(verified.amount).quantize(Decimal("0.01"))
            expected = {Decimal(payment.amount).quantize(Decimal("0.01"))}
            # Dev/UAT may STK a 1 KES test charge; production must match the policy premium.
            if not get_settings().is_production:
                stk_charged = (payment.provider_payload or {}).get("stk_amount")
                if stk_charged is not None:
                    expected.add(Decimal(str(stk_charged)).quantize(Decimal("0.01")))
            if received not in expected:
                payment.status = PaymentStatus.FAILED.value
                payment.failure_code = "AMOUNT_MISMATCH"
                payment.failure_message = "Webhook amount does not match payment intent"
                payment.version += 1
                await self.session.flush()
                await self.audit.record(
                    action="payment.webhook_amount_mismatch",
                    resource="payment",
                    resource_id=str(payment.id),
                    tenant_id=payment.tenant_id,
                    result="FAILURE",
                    metadata={
                        "expected": sorted(str(v) for v in expected),
                        "received": str(received),
                    },
                )
                return payment

        job = await self.jobs.create(
            tenant_id=payment.tenant_id,
            user_id=payment.initiated_by_user_id,
            job_type=JobType.PAYMENT_VERIFICATION,
        )
        payment.job_id = job.job_key
        payment.provider_payload = {
            **(payment.provider_payload or {}),
            "webhook": _redact_provider_payload(verified.raw),
        }

        if verified.success:
            payment.status = PaymentStatus.SUCCESS.value
            if late_success_after_user_cancel:
                payment.failure_code = None
                payment.failure_message = None
            payment.provider_receipt = verified.receipt or payment.provider_receipt
            payment.paid_at = datetime.now(UTC)
            payment.version += 1
            await self.session.flush()
            if payment.policy_id:
                # Never run Definite initiatePayment from the webhook — that would
                # STK the customer again after they already paid. Cert is finished
                # by issuance/pay once the UI sees SUCCESS.
                await self._on_success(
                    payment,
                    policy_id=payment.policy_id,
                    generate_certificate=False,
                )
            await self.jobs.transition(job, JobStatus.COMPLETED)
            await self.audit.record(
                action="payment.success",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=payment.tenant_id,
                user_id=payment.initiated_by_user_id,
                metadata={"receipt": payment.provider_receipt},
            )
        else:
            payment.status = PaymentStatus.FAILED.value
            payment.failure_code = verified.failure_code
            payment.failure_message = verified.failure_message
            payment.version += 1
            await self.session.flush()
            await self.jobs.transition(job, JobStatus.FAILED, error_code=verified.failure_code)
            await self.audit.record(
                action="payment.failed",
                resource="payment",
                resource_id=str(payment.id),
                tenant_id=payment.tenant_id,
                user_id=payment.initiated_by_user_id,
                result="FAILURE",
                metadata={"code": verified.failure_code},
            )
            await self._notify_payment_failed(payment)
        return payment

    async def sync_definite_stk_confirmation(self, payment: Payment) -> Payment:
        """Promote a pending Definite M-Pesa row once the insurer has approved the note.

        Definite owns the Safaricom callback. StarServe never receives that webhook.
        When ``initiatePayment`` already returned "Policy Approved. Proceed to Issue
        cert" (or the same phrase is stored on the policy), the local payment can
        move to SUCCESS so the wizard can issue the certificate.
        """
        from app.modules.insurance.definite_settlement import policy_note_confirmed
        from app.modules.payments.settlement import SettlementRail

        if payment.method != SettlementRail.DEFINITE_MPESA.value:
            return payment
        if payment.status not in {
            PaymentStatus.PENDING.value,
            PaymentStatus.INITIATED.value,
        }:
            return payment
        if payment.policy_id is None:
            return payment

        policy = await self.policies.get(payment.policy_id)
        summary = dict(policy.provider_payload_summary or {})
        if not policy_note_confirmed(summary):
            return payment

        locked = await self.repo.get_for_update(payment.id)
        if locked.status in TERMINAL_STATUSES:
            return locked
        if locked.status not in {
            PaymentStatus.PENDING.value,
            PaymentStatus.INITIATED.value,
        }:
            return locked

        job = await self.jobs.create(
            tenant_id=locked.tenant_id,
            user_id=locked.initiated_by_user_id,
            job_type=JobType.PAYMENT_VERIFICATION,
        )
        locked.job_id = job.job_key
        locked.status = PaymentStatus.SUCCESS.value
        locked.paid_at = datetime.now(UTC)
        locked.failure_code = None
        locked.failure_message = None
        locked.provider_payload = {
            **(locked.provider_payload or {}),
            "definite_stk_confirmed": summary.get("provider_payment_response") or True,
        }
        locked.version = int(locked.version or 1) + 1
        await self.session.flush()
        if locked.policy_id:
            await self._on_success(
                locked,
                policy_id=locked.policy_id,
                generate_certificate=False,
            )
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="payment.definite_stk_confirmed",
            resource="payment",
            resource_id=str(locked.id),
            tenant_id=locked.tenant_id,
            user_id=locked.initiated_by_user_id,
            metadata={"reference": locked.reference},
        )
        return locked

    async def confirm_receipt(self, payment_id: UUID, *, receipt: str) -> Payment:
        """Mark a pending STK payment SUCCESS using the customer's M-Pesa receipt.

        Finance-only reconcile when a provider callback never arrives. Disabled in
        production unless ``allow_receipt_confirm`` is explicitly true. Does not
        trust client amount.
        """
        import re

        from sqlalchemy import select

        from app.core.exceptions import AuthorizationError
        from app.modules.payments.models import Payment as PaymentModel

        self.ctx.require_staff_principal()
        self.ctx.require_active_tenant()
        self.ctx.require_any_permission("payment:reconcile")
        if not get_settings().receipt_confirm_allowed:
            raise AuthorizationError("Receipt confirmation is disabled in this environment")
        cleaned = re.sub(r"[^A-Za-z0-9]", "", (receipt or "").strip()).upper()
        # Safaricom receipts are letter-led alphanumerics (10 today); a free-form
        # string here would let finance settle a payment with any typed value.
        if not re.fullmatch(r"[A-Z][A-Z0-9]{7,11}", cleaned):
            raise ValidationAppError("Enter a valid M-Pesa receipt code from your SMS")

        payment = await self.repo.get_for_update(payment_id)
        self.ctx.assert_branch_access(getattr(payment, "branch_id", None))
        if payment.policy_id:
            policy = await self.policies.get_for_update(payment.policy_id)
            winner = await self.repo.find_success_for_policy(payment.policy_id)
            if winner is not None and winner.id != payment.id:
                raise ValidationAppError("Another payment already settled this policy")
            if policy.status != PolicyStatus.PENDING_PAYMENT.value:
                raise ValidationAppError("Policy is not awaiting payment")
        if payment.method not in ASYNC_STK_METHODS:
            raise ValidationAppError("Receipt confirmation is only for STK payments")
        if payment.status in TERMINAL_STATUSES:
            if payment.status == PaymentStatus.SUCCESS.value:
                return payment
            raise ValidationAppError(f"Payment is already {payment.status}")
        if payment.status not in {
            PaymentStatus.PENDING.value,
            PaymentStatus.INITIATED.value,
        }:
            raise ValidationAppError("Payment cannot be confirmed in its current state")

        dup = await self.session.scalar(
            select(PaymentModel).where(
                PaymentModel.tenant_id == self.ctx.tenant_id,
                PaymentModel.provider_receipt == cleaned,
                PaymentModel.id != payment.id,
                PaymentModel.status == PaymentStatus.SUCCESS.value,
            )
        )
        if dup is not None:
            raise ValidationAppError("That M-Pesa receipt was already used")

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.PAYMENT_VERIFICATION,
        )
        payment.job_id = job.job_key
        payment.status = PaymentStatus.SUCCESS.value
        payment.provider_receipt = cleaned
        payment.paid_at = datetime.now(UTC)
        payment.failure_code = None
        payment.failure_message = None
        payment.provider_payload = {
            **(payment.provider_payload or {}),
            "receipt_confirm": {
                "source": "customer_mpesa_sms",
                "receipt": cleaned,
                "confirmed_by": str(self.ctx.actor_user_id),
            },
        }
        payment.version += 1
        await self.session.flush()
        if payment.policy_id:
            await self._on_success(
                payment,
                policy_id=payment.policy_id,
                generate_certificate=False,
            )
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="payment.confirm_receipt",
            resource="payment",
            resource_id=str(payment.id),
            tenant_id=payment.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"receipt": cleaned, "method": payment.method},
        )
        return payment
