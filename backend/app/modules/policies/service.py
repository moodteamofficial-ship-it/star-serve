"""Policy service — issue from approved proposals; cancel with provider."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ValidationAppError
from app.core.security.context import SecurityContext
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.audit.service import AuditService
from app.modules.jobs.service import JobService
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.models import Policy
from app.modules.policies.repository import PolicyRepository
from app.modules.proposals.enums import ProposalStatus
from app.modules.proposals.repository import ProposalRepository


def to_public(row: Policy) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "customer_id": str(row.customer_id),
        "proposal_id": str(row.proposal_id) if row.proposal_id else None,
        "policy_number": row.policy_number,
        "product_code": row.product_code,
        "cover_option": row.cover_option,
        "vehicle_registration": row.vehicle_registration,
        "vehicle_make": row.vehicle_make,
        "vehicle_model": row.vehicle_model,
        "chassis_number": row.chassis_number,
        "engine_number": row.engine_number,
        "engine_rating": row.engine_rating,
        "make_code": row.make_code,
        "model_code": row.model_code,
        "agent_code": row.agent_code,
        "referral_code": getattr(row, "referral_code", None),
        "status": row.status,
        "channel": getattr(row, "channel", None) or "STAFF",
        "gross_premium": row.gross_premium,
        "sum_insured": row.sum_insured,
        "cover_start_date": row.cover_start_date,
        "cover_end_date": row.cover_end_date,
        "external_policy_ref": row.external_policy_ref,
        "certificate_ref": row.certificate_ref,
        "provider_note_oid": row.provider_note_oid,
        "provider_insured_item": row.provider_insured_item,
        "provider_document_number": row.provider_document_number,
        "provider_amount_to_pay": row.provider_amount_to_pay,
        "provider_payment_txn": row.provider_payment_txn,
        "cancellation_reason_code": row.cancellation_reason_code,
        "version": row.version,
        "job_id": row.job_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class PolicyService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.repo = PolicyRepository(session, ctx)
        self.proposals = ProposalRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)

    async def list(
        self, *, page: int, limit: int, query: str | None, status: str | None
    ) -> tuple[list[Policy], int]:
        return await self.repo.search(
            query=query, status=status, offset=(page - 1) * limit, limit=limit
        )

    async def get(self, policy_id: UUID) -> Policy:
        return await self.repo.get(policy_id)

    async def issue_from_proposal(self, proposal_id: UUID) -> Policy:
        """Create a local policy shell from an approved proposal (pre-payment)."""
        self.ctx.require_active_tenant()
        proposal = await self.proposals.get(proposal_id)
        if proposal.status != ProposalStatus.APPROVED.value:
            raise ValidationAppError("Only approved proposals can be issued as policies")
        if proposal.gross_premium is None:
            raise ValidationAppError("Proposal missing authoritative premium")

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            job_type=JobType.GENERIC,
        )
        policy_number = f"POL-{uuid4().hex[:10].upper()}"
        from app.core.security.branch_scope import resolve_authorized_branch

        self.ctx.assert_branch_access(getattr(proposal, "branch_id", None))
        branch_id = await resolve_authorized_branch(
            self.ctx, self.session, getattr(proposal, "branch_id", None)
        )
        policy = Policy(
            tenant_id=self.ctx.tenant_id,
            customer_id=proposal.customer_id,
            proposal_id=proposal.id,
            branch_id=branch_id,
            intermediary_id=proposal.intermediary_id,
            created_by_user_id=self.ctx.user_id,
            policy_number=policy_number,
            product_code=proposal.product_code,
            cover_option=proposal.cover_option,
            vehicle_registration=proposal.vehicle_registration,
            vehicle_make=proposal.vehicle_make,
            vehicle_model=proposal.vehicle_model,
            status=PolicyStatus.PENDING_PAYMENT.value,
            gross_premium=proposal.gross_premium,
            sum_insured=proposal.sum_insured,
            cover_start_date=proposal.cover_start_date,
            cover_end_date=proposal.cover_end_date,
            external_policy_ref=proposal.external_proposal_ref,
            provider_payload_summary={},
            job_id=job.job_key,
        )
        await self.repo.add(policy)
        proposal.status = ProposalStatus.CONVERTED.value
        proposal.version += 1
        await self.session.flush()
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="policy.issue_from_proposal",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={
                "proposal_id": str(proposal.id),
                "policy_number": policy.policy_number,
                "gross_premium": str(policy.gross_premium),
            },
        )
        return policy

    async def activate(self, policy_id: UUID) -> Policy:
        """Mark policy active only after a verified SUCCESS payment."""
        self.ctx.require_active_tenant()
        policy = await self.repo.get(policy_id)
        if policy.status not in {
            PolicyStatus.PENDING_PAYMENT.value,
            PolicyStatus.PENDING_CERTIFICATE.value,
        }:
            raise ValidationAppError("Policy cannot be activated in its current state")
        from app.modules.payments.enums import PaymentStatus
        from app.modules.payments.repository import PaymentRepository

        paid = await PaymentRepository(self.session, self.ctx).find_latest_for_policy(
            policy.id, status=PaymentStatus.SUCCESS.value
        )
        if paid is None:
            raise ValidationAppError("Policy cannot be activated without a successful payment")
        policy.status = PolicyStatus.ACTIVE.value
        policy.version += 1
        await self.session.flush()
        await self.audit.record(
            action="policy.activate",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"payment_id": str(paid.id)},
        )
        return policy

    async def cancel(self, policy_id: UUID, *, reason_code: str, notes: str | None) -> Policy:
        self.ctx.require_active_tenant()
        policy = await self.repo.get(policy_id)
        if policy.status == PolicyStatus.CANCELLED.value:
            raise ValidationAppError("Policy is already cancelled")
        if policy.status not in {
            PolicyStatus.ACTIVE.value,
            PolicyStatus.PENDING_PAYMENT.value,
            PolicyStatus.PENDING_CERTIFICATE.value,
        }:
            raise ValidationAppError("Policy cannot be cancelled in its current state")

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            job_type=JobType.POLICY_CANCELLATION,
        )
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="cancelPolicy")
        try:
            remote = await self.provider.cancel_policy(
                {
                    "policyNumber": policy.policy_number,
                    "policyId": policy.external_policy_ref,
                    "reasonCode": reason_code,
                    "registration": policy.vehicle_registration,
                }
            )
        except Exception:
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="POLICY_CANCEL_PROVIDER_FAILED",
            )
            raise
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="cancelPolicy")

        policy.status = PolicyStatus.CANCELLED.value
        policy.cancellation_reason_code = reason_code
        policy.cancelled_at = datetime.now(UTC)
        policy.cancelled_by_user_id = self.ctx.user_id
        policy.notes = notes
        policy.provider_payload_summary = (
            {"cancel": remote} if isinstance(remote, dict) else {"cancel": True}
        )
        policy.version += 1
        policy.job_id = job.job_key
        await self.session.flush()
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="policy.cancel",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"reason_code": reason_code},
        )
        return policy

    async def refresh_details(self, policy_id: UUID) -> dict[str, Any]:
        self.ctx.require_active_tenant()
        policy = await self.repo.get(policy_id)
        remote = await self.provider.get_policy_details(
            {
                "policyNumber": policy.policy_number,
                "policyId": policy.external_policy_ref or "",
            }
        )
        await self.audit.record(
            action="policy.details_refresh",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
        )
        from app.core.security.provider_payload import redact_provider_public

        return {
            "policy": to_public(policy),
            "provider": redact_provider_public(
                remote if isinstance(remote, dict) else {"data": remote}
            ),
        }
