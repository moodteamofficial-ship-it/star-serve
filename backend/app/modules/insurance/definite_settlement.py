"""Idempotent Definite initiatePayment — at most one successful settle per note."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import JobType
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.core.security.context import SecurityContext
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.customers.repository import CustomerRepository
from app.modules.jobs.models import Job
from app.modules.jobs.service import JobService
from app.modules.payments.settlement import DefinitePaymentMethod
from app.modules.insurance.provider_fields import definite_holder_fields, extract_holder_email
from app.modules.policies.models import Policy
from app.modules.policies.repository import PolicyRepository

logger = get_logger(__name__)

# Definite initiatePayment HTTP 200 is not enough for customer STK (method 1).
# These phrases mean the note is paid and generateCertificate may run.
_NOTE_CONFIRMED_TOKENS = (
    "already paid",
    "already approved",
    "proceed to issue",
    "policy approved",
)
# Idempotent "we already have this charge" replies — do not send another STK.
_NOTE_ALREADY_SETTLED_TOKENS = _NOTE_CONFIRMED_TOKENS + (
    "already exists",
    "duplicate",
)


def definite_note_confirmed(remote: Any) -> bool:
    """True when Definite says the proposal note is paid / ready for a cert."""
    if not isinstance(remote, dict):
        return False
    message = str(remote.get("message") or remote.get("Message") or "").lower()
    return any(token in message for token in _NOTE_CONFIRMED_TOKENS)


class DefiniteSettlementService:
    """Approve a Definite proposal note exactly once (wallet or STK)."""

    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.policies = PolicyRepository(session, ctx)
        self.jobs = JobService(session, ctx)

    async def approve_note_once(
        self,
        policy: Policy,
        *,
        definite_payment_method: DefinitePaymentMethod | int,
        phone: str | None = None,
        receipt: str | None = None,
        job: Job | None = None,
    ) -> dict[str, Any]:
        """Call Definite ``initiatePayment`` at most once per policy note.

        Returns ``{"approved": True, "skipped": bool, "confirmed": bool, "receipt": str}``.
        ``confirmed`` is true only when Definite says the note is paid / ready
        for a certificate — not merely that an STK was accepted.
        """
        from app.core.config import get_settings

        policy = await self.policies.get_for_update(policy.id)
        method_code = int(definite_payment_method)
        summary = dict(policy.provider_payload_summary or {})
        settings = get_settings()

        if summary.get("provider_payment_approved"):
            stored_method = int(summary.get("definite_payment_method") or method_code)
            # Method 0 on UAT does not fund the note (and can 500 with a Node
            # ``fetch failed``). Re-run wallet settle so generateCertificate works.
            stored_amt_raw = summary.get("provider_amount_paid")
            try:
                stored_amt = int(round(float(stored_amt_raw))) if stored_amt_raw is not None else None
            except (TypeError, ValueError):
                stored_amt = None
            premium = float(policy.gross_premium or summary.get("amount_to_pay") or 0)
            underpaid_live = (
                not settings.definite_is_uat
                and premium > 1
                and not summary.get("provider_live_full_settle_attempted")
                and (stored_amt == 1 or stored_amt is None)
            )
            if (
                stored_method == int(DefinitePaymentMethod.ALREADY_PAID)
                and method_code == int(DefinitePaymentMethod.WALLET)
            ) or underpaid_live:
                summary["provider_payment_approved"] = False
                summary["provider_payment_confirmed"] = False
                summary["provider_payment_rewritten_from"] = stored_method
                if underpaid_live:
                    summary["provider_payment_rewrite_reason"] = "live_underpaid_amount"
                    summary["provider_live_full_settle_attempted"] = True
                policy.provider_payload_summary = summary
                await self.session.flush()
            else:
                if job is not None:
                    await self.jobs.add_event(
                        job,
                        "EXTERNAL_REQUEST_SKIPPED",
                        message="initiatePayment already approved for this note",
                    )
                return {
                    "approved": True,
                    "skipped": True,
                    "confirmed": policy_note_confirmed(summary),
                    "receipt": str(
                        policy.provider_payment_txn or summary.get("provider_payment_txn") or ""
                    ),
                    "definite_payment_method": int(
                        summary.get("definite_payment_method") or method_code
                    ),
                }

        proposal_ref, note_oid, insured_item, document_number, amount_to_pay = (
            self._extract_note_refs(policy, summary)
        )
        if not proposal_ref or not note_oid:
            raise ValidationAppError(
                "Policy is missing Definite proposal/note details required for payment",
                details=[{"proposal": proposal_ref, "note_oid": note_oid}],
            )
        if not insured_item or not document_number:
            raise ValidationAppError(
                "Policy is missing Definite insured item / document number for initiatePayment",
                details=[
                    {
                        "insured_item": insured_item,
                        "document_number": document_number,
                    }
                ],
            )

        resolved_phone = phone
        customer = None
        if policy.customer_id:
            try:
                customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                    policy.customer_id
                )
                if not resolved_phone:
                    resolved_phone = customer.phone
            except Exception as exc:
                logger.warning(
                    "definite_settle_holder_lookup_failed",
                    policy_id=str(policy.id),
                    error_type=type(exc).__name__,
                )
                customer = None
        if settings.definite_is_uat:
            resolved_phone = resolved_phone or settings.definite_assurance_test_phone
        holder_fields = definite_holder_fields(summary, customer)
        holder_email = extract_holder_email(customer, summary)
        if holder_fields.get("PolicyHolder"):
            summary["definite_client_oid"] = holder_fields["PolicyHolder"]

        # Deterministic receipt — same note always reuses the same txn id
        mpesa_txn = str(
            receipt
            or policy.provider_payment_txn
            or summary.get("provider_payment_txn")
            or f"SSN{note_oid}"
        ).strip()[:20]

        # Claim before network I/O so a parallel retry cannot open a second settle.
        summary["provider_payment_txn"] = mpesa_txn
        summary["provider_payment_started"] = True
        summary["definite_payment_method"] = method_code
        try:
            summary["provider_amount_paid"] = int(round(float(amount_to_pay or 0)))
        except (TypeError, ValueError):
            summary["provider_amount_paid"] = 0
        policy.provider_payload_summary = summary
        policy.provider_payment_txn = mpesa_txn
        await self.session.flush()

        own_job = job
        if own_job is None:
            own_job = await self.jobs.create(
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                job_type=JobType.PAYMENT_VERIFICATION,
            )

        await self.jobs.add_event(
            own_job,
            "EXTERNAL_REQUEST_STARTED",
            message=f"initiatePayment method={method_code}",
        )

        try:
            remote = await self.provider.initiate_provider_payment(
                {
                    "InsuredItem": insured_item,
                    "Proposal": proposal_ref,
                    "PhoneNumber": resolved_phone,
                    "PaymentMethod": method_code,
                    "MpesaTransaction": mpesa_txn,
                    "AmountPaid": amount_to_pay,
                    "note": f"StarServe - {policy.vehicle_registration}",
                    "DocumentNumber": document_number,
                    "noteOID": note_oid,
                    **holder_fields,
                    **({"email": holder_email} if holder_email else {}),
                }
            )
        except Exception as exc:
            summary = dict(policy.provider_payload_summary or {})
            summary["provider_payment_error"] = str(exc)[:400]
            # Keep started + same MpesaTransaction so a retry cannot invent a new
            # wallet/STK charge id for this note.
            policy.provider_payload_summary = summary
            await self.session.flush()
            raise

        ok = bool(isinstance(remote, dict) and remote.get("success") is not False)
        message = str((remote or {}).get("message") or "") if isinstance(remote, dict) else ""
        message_l = message.lower()
        from app.integrations.insurance.definite_assurance.client import (
            provider_message_is_internal,
            public_definite_message,
        )

        if provider_message_is_internal(message):
            ok = False
        if not ok:
            # Treat Definite "already settled" style replies as success (idempotent).
            ok = any(token in message_l for token in _NOTE_ALREADY_SETTLED_TOKENS)
            if provider_message_is_internal(message):
                ok = False
        if not ok:
            summary = dict(policy.provider_payload_summary or {})
            summary["provider_payment_error"] = message[:400] or "initiatePayment failed"
            policy.provider_payload_summary = summary
            await self.session.flush()
            raise ValidationAppError(
                public_definite_message(message)
                if message
                else "Definite initiatePayment was not approved",
            )

        confirmed = definite_note_confirmed(remote if isinstance(remote, dict) else None)
        # Agency wallet debit is settlement: HTTP success means the note is paid.
        if method_code == int(DefinitePaymentMethod.WALLET) and ok:
            confirmed = True
        summary = dict(policy.provider_payload_summary or {})
        summary["provider_payment_approved"] = True
        summary["provider_payment_confirmed"] = confirmed
        summary["provider_payment_response"] = (
            {k: remote.get(k) for k in ("success", "message") if isinstance(remote, dict)}
            if isinstance(remote, dict)
            else {"raw": str(remote)[:200]}
        )
        summary["definite_payment_method"] = method_code
        summary.pop("provider_payment_error", None)
        policy.provider_payload_summary = summary
        policy.provider_payment_txn = mpesa_txn
        await self.session.flush()

        await self.jobs.add_event(
            own_job,
            "EXTERNAL_REQUEST_SUCCEEDED",
            message=f"initiatePayment method={method_code}",
        )
        return {
            "approved": True,
            "skipped": False,
            "confirmed": confirmed,
            "receipt": mpesa_txn,
            "definite_payment_method": method_code,
            "provider": remote if isinstance(remote, dict) else {"data": remote},
        }

    @staticmethod
    def _extract_note_refs(
        policy: Policy, summary: dict[str, Any]
    ) -> tuple[Any, Any, Any, Any, Any]:
        proposal_blob = summary.get("proposal") if isinstance(summary.get("proposal"), dict) else {}
        details = (
            proposal_blob.get("proposalDetails")
            if isinstance(proposal_blob.get("proposalDetails"), dict)
            else {}
        )
        proposal_ref = (
            policy.external_policy_ref
            or summary.get("proposal_oid")
            or details.get("OID")
            or proposal_blob.get("proposalId")
        )
        note_oid = (
            policy.provider_note_oid
            or summary.get("note_oid")
            or summary.get("Note")
            or summary.get("noteOID")
            or details.get("Note")
            or details.get("noteOID")
        )
        insured_item = (
            policy.provider_insured_item
            or summary.get("insured_item")
            or details.get("InsuredItem")
            or proposal_blob.get("InsuredItem")
        )
        document_number = (
            policy.provider_document_number
            or summary.get("document_number")
            or details.get("DocumentNumber")
            or proposal_blob.get("DocumentNumber")
        )
        amount_to_pay = (
            policy.provider_amount_to_pay
            or summary.get("amount_to_pay")
            or details.get("AmountToPay")
            or policy.gross_premium
        )
        return proposal_ref, note_oid, insured_item, document_number, amount_to_pay


def policy_note_confirmed(summary: dict[str, Any] | None) -> bool:
    if not summary:
        return False
    if summary.get("provider_payment_confirmed"):
        return True
    return definite_note_confirmed(summary.get("provider_payment_response"))
