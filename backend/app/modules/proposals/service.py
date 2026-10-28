"""Proposal workflow service.

Mandatory path:
customer → policy check → double insurance → premium (provider) → create/submit → approve
Premium amounts are NEVER taken from the client.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ConflictError, ValidationAppError
from app.core.idempotency.service import IdempotencyService
from app.core.security.context import SecurityContext
from app.core.validation.identity import normalize_vehicle_registration
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.audit.service import AuditService
from app.modules.customers.repository import CustomerRepository
from app.modules.intermediaries.repository import IntermediaryRepository
from app.modules.jobs.models import IdempotencyKey
from app.modules.jobs.service import JobService
from app.modules.proposals.enums import ProposalStatus
from app.modules.proposals.models import Proposal
from app.modules.proposals.repository import ProposalRepository
from app.modules.proposals.schemas import ProposalCreateRequest


def to_public(row: Proposal) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "customer_id": str(row.customer_id),
        "intermediary_id": str(row.intermediary_id) if row.intermediary_id else None,
        "product_code": row.product_code,
        "cover_option": row.cover_option,
        "cover_period": row.cover_period,
        "transaction_type": row.transaction_type,
        "vehicle_registration": row.vehicle_registration,
        "vehicle_make": row.vehicle_make,
        "vehicle_model": row.vehicle_model,
        "vehicle_year": row.vehicle_year,
        "chassis_number": row.chassis_number,
        "engine_number": row.engine_number,
        "engine_rating": row.engine_rating,
        "make_code": row.make_code,
        "model_code": row.model_code,
        "agent_code": row.agent_code,
        "intermediary_name": row.intermediary_name,
        "ira_number": row.ira_number,
        "sum_insured": row.sum_insured,
        "basic_premium": row.basic_premium,
        "phcf": row.phcf,
        "training_levy": row.training_levy,
        "stamp_duty": row.stamp_duty,
        "gross_premium": row.gross_premium,
        "status": row.status,
        "channel": getattr(row, "channel", None) or "STAFF",
        "double_insurance_clear": row.double_insurance_clear,
        "external_proposal_ref": row.external_proposal_ref,
        "provider_note_oid": row.provider_note_oid,
        "provider_insured_item": row.provider_insured_item,
        "provider_document_number": row.provider_document_number,
        "provider_amount_to_pay": row.provider_amount_to_pay,
        "cover_start_date": row.cover_start_date,
        "cover_end_date": row.cover_end_date,
        "version": row.version,
        "job_id": row.job_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class ProposalService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.repo = ProposalRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)
        self.idempotency = IdempotencyService(session)

    async def list(
        self, *, page: int, limit: int, query: str | None, status: str | None
    ) -> tuple[list[Proposal], int]:
        return await self.repo.search(
            query=query, status=status, offset=(page - 1) * limit, limit=limit
        )

    async def get(self, proposal_id: UUID) -> Proposal:
        return await self.repo.get(proposal_id)

    async def create(
        self,
        body: ProposalCreateRequest,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.ctx.require_active_tenant()
        payload = body.model_dump(mode="json")
        idem_record: IdempotencyKey | None = None
        if idempotency_key:
            started = await self.idempotency.begin(
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                key=idempotency_key,
                operation="proposal.create",
                request_hash=IdempotencyService.hash_request(payload),
            )
            if isinstance(started, dict):
                return started
            idem_record = started

        customer_id = UUID(body.customer_id)
        customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
            customer_id
        )
        from app.core.security.branch_scope import resolve_authorized_branch

        branch_id = await resolve_authorized_branch(
            self.ctx, self.session, getattr(customer, "branch_id", None)
        )

        intermediary_id = UUID(body.intermediary_id) if body.intermediary_id else None
        if intermediary_id:
            await IntermediaryRepository(self.session, self.ctx).get_active_by_id(intermediary_id)

        registration = normalize_vehicle_registration(body.vehicle_registration)
        product_code = body.product_code.strip().upper()
        existing = await self.repo.find_open_for_vehicle_product(
            registration=registration, product_code=product_code
        )
        if existing:
            raise ConflictError(
                "An open proposal already exists for this vehicle and product",
                details=[{"proposal_id": str(existing.id), "status": existing.status}],
            )

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            job_type=JobType.PROPOSAL_CREATION,
        )

        proposal = Proposal(
            tenant_id=self.ctx.tenant_id,
            customer_id=customer_id,
            intermediary_id=intermediary_id,
            branch_id=branch_id,
            created_by_user_id=self.ctx.user_id,
            product_code=product_code,
            cover_option=body.cover_option.strip(),
            cover_period=body.cover_period.strip(),
            transaction_type=body.transaction_type.strip().upper(),
            vehicle_registration=registration,
            vehicle_make=body.vehicle_make.strip().upper(),
            vehicle_model=body.vehicle_model.strip() if body.vehicle_model else None,
            vehicle_year=body.vehicle_year,
            sum_insured=body.sum_insured,
            capacity=body.capacity,
            tonnage=body.tonnage,
            cover_start_date=body.cover_start_date,
            notes=body.notes,
            status=ProposalStatus.DRAFT.value,
            job_id=job.job_key,
            double_insurance_result={},
            policy_check_result={},
        )
        await self.repo.add(proposal)
        await self.session.flush()

        # 1) Policy check
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkPolicy")
        try:
            policy_check = await self.provider.check_policy(
                {
                    "registration": registration,
                    "product": product_code,
                    "IDNumber": str(customer_id),
                }
            )
        except Exception:
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="POLICY_CHECK_FAILED",
                error_message="Policy check unavailable",
            )
            raise
        proposal.policy_check_result = (
            policy_check if isinstance(policy_check, dict) else {"data": policy_check}
        )
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="checkPolicy")

        # 2) Double insurance
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="checkDoubleInsurance")
        try:
            double = await self.provider.check_double_insurance(
                {
                    "registration": registration,
                    "product": product_code,
                }
            )
        except Exception:
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="DOUBLE_INSURANCE_CHECK_FAILED",
            )
            raise
        proposal.double_insurance_result = double if isinstance(double, dict) else {"data": double}
        proposal.double_insurance_clear = _is_double_insurance_clear(double)
        proposal.status = ProposalStatus.DOUBLE_INSURANCE_CHECKED.value
        proposal.version += 1
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            message="checkDoubleInsurance",
            metadata={"clear": proposal.double_insurance_clear},
        )
        from app.core.config import get_settings
        from app.modules.insurance.policy_rules import should_enforce_double_insurance

        if proposal.double_insurance_clear is False and should_enforce_double_insurance(
            get_settings()
        ):
            await self.jobs.transition(
                job,
                JobStatus.FAILED,
                error_code="DOUBLE_INSURANCE_DETECTED",
                error_message="Double insurance check failed",
            )
            await self.audit.record(
                action="proposal.double_insurance_blocked",
                resource="proposal",
                resource_id=str(proposal.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                result="FAILURE",
            )
            raise ValidationAppError(
                "Double insurance was detected for this vehicle/product",
                details=[{"proposal_id": str(proposal.id)}],
            )
        if proposal.double_insurance_clear is False:
            # UAT/dev soft-check — record and continue
            proposal.double_insurance_clear = True
            proposal.double_insurance_result = {
                **(proposal.double_insurance_result or {}),
                "_bypassed_for_uat": True,
            }
            await self.jobs.add_event(
                job,
                "DOUBLE_INSURANCE_BYPASSED",
                message="Double insurance soft-check bypassed for non-LIVE environment",
            )

        # 3) Authoritative premium
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="calculatePremium")
        premium = await self.provider.calculate_premium(
            {
                "sum_insured": float(body.sum_insured),
                "capacity": float(body.capacity) if body.capacity is not None else None,
                "tonnage": float(body.tonnage) if body.tonnage is not None else None,
                "cover_period": body.cover_period,
                "product": product_code,
                "cover_option": body.cover_option,
                "transaction_type": body.transaction_type,
            }
        )
        proposal.basic_premium = _dec(premium.get("basic_premium"))
        proposal.phcf = _dec(premium.get("phcf"))
        proposal.training_levy = _dec(premium.get("training_levy"))
        proposal.stamp_duty = _dec(premium.get("stamp_duty"))
        proposal.gross_premium = _dec(premium.get("gross_premium"))
        if proposal.gross_premium is None:
            raise ValidationAppError("Insurance provider did not return a gross premium")
        proposal.status = ProposalStatus.PREMIUM_CALCULATED.value
        proposal.version += 1
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="calculatePremium")

        # 4) Create at provider when supported
        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="createProposal")
        provider_payload = {
            "product": product_code,
            "coverOption": body.cover_option,
            "coverPeriod": body.cover_period,
            "transactionType": body.transaction_type,
            "registration": registration,
            "make": proposal.vehicle_make,
            "model": proposal.vehicle_model,
            "sumInsured": float(proposal.sum_insured),
            "customerId": str(customer_id),
            "grossPremium": float(proposal.gross_premium),
        }
        try:
            remote = await self.provider.create_proposal(provider_payload)
        except Exception:
            # Local proposal retained for retry; mark waiting
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="PROPOSAL_PROVIDER_CREATE_FAILED",
            )
            await self.session.flush()
            raise

        if isinstance(remote, dict):
            data = remote.get("data") if isinstance(remote.get("data"), dict) else {}
            ref = remote.get("proposalId") or remote.get("id") or data.get("proposalId")
            if ref:
                proposal.external_proposal_ref = str(ref)
        proposal.status = ProposalStatus.SUBMITTED.value
        proposal.submitted_at = datetime.now(UTC)
        proposal.version += 1
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="createProposal")
        await self.jobs.transition(job, JobStatus.COMPLETED, progress=100)

        await self.audit.record(
            action="proposal.create",
            resource="proposal",
            resource_id=str(proposal.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={
                "vehicle_registration": registration,
                "product_code": product_code,
                "gross_premium": str(proposal.gross_premium),
            },
        )
        await self.session.flush()
        result = {"proposal": to_public(proposal), "job_id": job.job_key}
        if idem_record is not None:
            await self.idempotency.complete(
                idem_record, response_body=result, job_id=job.job_key
            )
        return result

    async def approve(self, proposal_id: UUID) -> Proposal:
        self.ctx.require_active_tenant()
        proposal = await self.repo.get(proposal_id)
        if proposal.status != ProposalStatus.SUBMITTED.value:
            raise ValidationAppError("Only submitted proposals can be approved")
        if proposal.gross_premium is None:
            raise ValidationAppError("Proposal is missing authoritative premium")
        if proposal.double_insurance_clear is False:
            raise ValidationAppError("Proposal failed double-insurance checks")

        proposal.status = ProposalStatus.APPROVED.value
        proposal.approved_at = datetime.now(UTC)
        proposal.approved_by_user_id = self.ctx.user_id
        proposal.version += 1
        await self.session.flush()
        await self.audit.record(
            action="proposal.approve",
            resource="proposal",
            resource_id=str(proposal.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
        )
        return proposal

    async def reject(self, proposal_id: UUID, *, reason: str) -> Proposal:
        self.ctx.require_active_tenant()
        proposal = await self.repo.get(proposal_id)
        if proposal.status not in {
            ProposalStatus.SUBMITTED.value,
            ProposalStatus.PREMIUM_CALCULATED.value,
            ProposalStatus.DOUBLE_INSURANCE_CHECKED.value,
        }:
            raise ValidationAppError("Proposal cannot be rejected in its current state")
        proposal.status = ProposalStatus.REJECTED.value
        proposal.notes = (proposal.notes or "") + f"\nRejected: {reason}"
        proposal.version += 1
        await self.session.flush()
        await self.audit.record(
            action="proposal.reject",
            resource="proposal",
            resource_id=str(proposal.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
            metadata={"reason": reason},
        )
        return proposal

    async def cancel(self, proposal_id: UUID) -> Proposal:
        self.ctx.require_active_tenant()
        proposal = await self.repo.get(proposal_id)
        if proposal.status in {
            ProposalStatus.CONVERTED.value,
            ProposalStatus.CANCELLED.value,
        }:
            raise ValidationAppError("Proposal cannot be cancelled in its current state")
        proposal.status = ProposalStatus.CANCELLED.value
        proposal.version += 1
        await self.session.flush()
        await self.audit.record(
            action="proposal.cancel",
            resource="proposal",
            resource_id=str(proposal.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.user_id,
        )
        return proposal


def _is_double_insurance_clear(payload: Any) -> bool:
    """Shared with the issuance wizard — see ``insurance.policy_rules``."""
    from app.modules.insurance.policy_rules import is_double_insurance_clear

    return is_double_insurance_clear(payload)
