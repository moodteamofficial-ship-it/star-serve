"""End-to-end issuance orchestration for the quote wizard."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import IdempotencyConflictError, ValidationAppError
from app.core.idempotency.service import IdempotencyService
from app.core.security.branch_scope import resolve_authorized_branch
from app.core.security.context import SecurityContext
from app.core.security.provider_config import require_configured_definite_agent
from app.core.validation.identity import normalize_vehicle_registration
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.audit.service import AuditService
from app.modules.certificates.service import CertificateService, to_public as cert_to_public
from app.modules.customers.repository import CustomerRepository
from app.modules.insurance.issuance_schemas import (
    IssuanceClientRequest,
    IssuancePayRequest,
    IssuanceSubmitRequest,
)
from app.modules.insurance.policy_rules import (
    evaluate_double_insurance as _evaluate_double_insurance,
    is_double_insurance_clear as _is_double_insurance_clear,
    should_enforce_double_insurance as _should_enforce_double_insurance,
)
from app.modules.insurance.provider_fields import (
    as_optional_decimal,
    as_optional_int,
    as_optional_str,
    extract_definite_client_oid,
    parse_provider_datetime,
)
from app.modules.insurance.schemas import EnsureClientRequest
from app.modules.insurance.service import InsuranceOrchestrationService
from app.modules.jobs.service import JobService
from app.modules.payments.enums import (
    ASYNC_STK_METHODS,
    USER_CANCELLED_PAYMENT,
    PaymentStatus,
)
from app.modules.payments.schemas import PaymentInitiateRequest
from app.modules.payments.service import PaymentService, to_public as payment_to_public
from app.modules.payments.settlement import GUEST_ALLOWED_RAILS, resolve_settlement_plan
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.models import Policy
from app.modules.policies.repository import PolicyRepository
from app.modules.policies.service import to_public as policy_to_public
from app.modules.products.cache import ReferenceDataCache
from app.modules.proposals.enums import ProposalStatus
from app.modules.proposals.models import Proposal
from app.modules.proposals.repository import ProposalRepository
from app.modules.proposals.service import to_public as proposal_to_public

_NAIROBI = ZoneInfo("Africa/Nairobi")


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def resolve_proposal_client(*, is_guest: bool, customer: Any) -> Any | None:
    """Bind Definite ``Client`` from the server-stored customer record.

    Guests cannot pick an arbitrary OID from the request. They may only use the
    numeric OID returned by *our* ``createClient`` for this session (policy
    holder). They must not fall back to national ID — that can attach another
    person's Definite client. Staff may fall back to national ID when no OID
    is stored.
    """
    oid = extract_definite_client_oid(customer)
    if oid is not None:
        return str(oid)
    if is_guest:
        return None
    return str(customer.id_number)


def guest_submit_idempotency_key(
    *,
    session_id: Any,
    customer_id: Any,
    registration: str,
    product_code: str,
    terms: str = "",
) -> str:
    key = f"guest-submit:{session_id}:{customer_id}:{registration}:{product_code}"
    return f"{key}:{terms}" if terms else key


def _quote_terms(
    *, cover_option_id: Any, period: Any, capacity: Any, sum_insured: Any
) -> tuple[str, str, str, str]:
    """Pricing inputs that must match before an unpaid guest proposal is reused."""

    def whole(value: Any) -> str:
        try:
            return str(int(Decimal(str(value or 0))))
        except Exception:
            return str(value or "")

    return (
        str(cover_option_id or "").strip(),
        str(period or "").strip().lower(),
        whole(capacity),
        whole(sum_insured),
    )


class IssuanceService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
        cache: ReferenceDataCache | None = None,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.cache = cache or ReferenceDataCache()
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)
        self.insurance = InsuranceOrchestrationService(session, ctx, provider, self.cache)
        self.proposals = ProposalRepository(session, ctx)
        self.policies = PolicyRepository(session, ctx)

    async def ensure_client(self, body: IssuanceClientRequest) -> dict[str, Any]:
        return await self.insurance.ensure_client(
            EnsureClientRequest(
                first_name=body.first_name,
                last_name=body.last_name,
                other_names=body.other_names,
                id_number=body.id_number,
                phone=body.phone,
                kra_pin=body.kra_pin,
                email=body.email,
                create_if_missing=True,
            )
        )

    async def _resolve_intermediary(self, body: IssuanceSubmitRequest):
        """Return an approved tenant intermediary for certificate + commission attribution.

        Guests may only attribute via a validated 6-digit agent code (QR / session).
        """
        from app.core.exceptions import ResourceNotFoundError
        from app.modules.intermediaries.models import Intermediary
        from app.modules.intermediaries.repository import IntermediaryRepository

        repo = IntermediaryRepository(self.session, self.ctx)
        row: Intermediary | None = None
        if self.ctx.is_guest:
            code = (body.agent_code or "").strip()
            if not code:
                return None
            row = await repo.find_by_agent_code(code)
            if row is None or str(row.status).upper() != "APPROVED":
                raise ValidationAppError("That agent code is not valid")
            return row

        if not (body.intermediary_id or "").strip():
            return None
        try:
            row = await repo.get_active_by_id(UUID(body.intermediary_id.strip()))
        except (ValueError, ResourceNotFoundError) as exc:
            raise ValidationAppError("Select a registered intermediary") from exc
        if str(row.status).upper() != "APPROVED":
            raise ValidationAppError("That intermediary is not approved for issuance")
        return row

    async def _resolve_referral_code(
        self, body: IssuanceSubmitRequest, customer: Any
    ) -> str | None:
        """Validated referral code, or None. Your own code is ignored, not an error."""
        from app.core.validation.identity import normalize_id_number
        from app.modules.referrals.service import ReferralService

        raw = (body.referral_code or "").strip()
        if not raw:
            return None
        row = await ReferralService(self.session).resolve(raw)
        if row is None:
            raise ValidationAppError("That referral code is not valid")
        if row.id_number == normalize_id_number(customer.id_number):
            return None
        return row.code

    async def _referral_summary(self, policy: Policy, customer: Any) -> dict[str, Any]:
        """Credit the buyer can spend on this cover (M-Pesa / BirdView only).

        Monthly cover always adds a fixed agency referral cost on top of Definite's
        total; that fee is charged to the customer and is not remitted to Definite.
        """
        from app.modules.insurance.fees import monthly_referral_cost, resolve_cover_period
        from app.modules.referrals.service import ReferralService

        referral_cost = monthly_referral_cost(
            await resolve_cover_period(self.session, self.ctx, policy)
        )
        gross = Decimal(policy.gross_premium or 0)
        service = ReferralService(self.session)
        out: dict[str, Any] = {
            "code_applied": policy.referral_code,
            "credit_balance": "0.00",
            "discount": "0.00",
            "referral_cost": str(referral_cost),
            "amount_payable": str(gross + referral_cost),
        }
        if customer is None or policy.gross_premium is None:
            return out
        try:
            async with self.session.begin_nested():
                balance = await service.balance(customer.tenant_id, customer.id_number)
                discount = await service.available_discount(
                    tenant_id=customer.tenant_id,
                    id_number=customer.id_number,
                    gross=gross + referral_cost,
                )
        except Exception:
            return out
        out["credit_balance"] = str(balance)
        out["discount"] = str(discount)
        out["amount_payable"] = str(gross + referral_cost - discount)
        return out

    async def submit(self, body: IssuanceSubmitRequest) -> dict[str, Any]:
        """Vehicle step: checks → premium → DA proposal → local policy PENDING_PAYMENT."""
        self.ctx.require_active_tenant()
        from app.modules.system_config.service import SystemConfigService

        await SystemConfigService(self.session).require_service("issuance")
        customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
            UUID(body.customer_id)
        )
        from app.modules.guest.ownership import require_owned_customer_ctx

        require_owned_customer_ctx(self.ctx, customer)
        registration = normalize_vehicle_registration(body.vehicle_registration)
        intermediary = await self._resolve_intermediary(body)
        referral_code = await self._resolve_referral_code(body, customer)
        from app.modules.referrals.service import ReferralService

        # Only a guest's agent came from a QR scan; staff pick the issuing intermediary.
        await ReferralService(self.session).record_attribution(
            customer,
            intermediary=intermediary if self.ctx.is_guest else None,
            referral_code=referral_code,
        )
        intermediary_name = (intermediary.name or "").strip() or None if intermediary else None
        ira_number = (intermediary.kra_pin or "").strip() or None if intermediary else None
        product_code = body.product_code.strip().upper()

        idem_record = None
        if self.ctx.is_guest:
            terms = _quote_terms(
                cover_option_id=body.cover_option_id,
                period=_payment_interval(body.cover_period_used or body.cover_period),
                capacity=body.capacity,
                sum_insured=body.sum_insured,
            )
            reused = await self._reuse_guest_issuance(
                customer_id=customer.id,
                registration=registration,
                product_code=product_code,
                terms=terms,
            )
            if reused is not None:
                return reused
            idem = IdempotencyService(self.session)
            try:
                started = await idem.begin(
                    tenant_id=self.ctx.tenant_id,
                    user_id=None,
                    key=guest_submit_idempotency_key(
                        session_id=self.ctx.session_id,
                        customer_id=customer.id,
                        registration=registration,
                        product_code=product_code,
                        terms=":".join(terms),
                    ),
                    operation="guest.issuance.submit",
                    request_hash=IdempotencyService.hash_request(
                        {
                            "customer_id": str(customer.id),
                            "registration": registration,
                            "product_code": product_code,
                            "terms": list(terms),
                        }
                    ),
                )
            except IdempotencyConflictError:
                reused = await self._reuse_guest_issuance(
                    customer_id=customer.id,
                    registration=registration,
                    product_code=product_code,
                    terms=terms,
                )
                if reused is not None:
                    return reused
                raise ValidationAppError("This quote is already being submitted") from None
            if isinstance(started, dict):
                return started
            idem_record = started

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.PROPOSAL_CREATION,
        )

        await self.jobs.add_event(
            job,
            "EXTERNAL_REQUEST_STARTED",
            message="checkPolicy+checkDoubleInsurance+calculatePremium",
        )
        policy_check, double, premium = await asyncio.gather(
            self.provider.check_policy({"registration": registration}),
            self.provider.check_double_insurance(
                {"chasis": body.chassis_number, "reg": registration}
            ),
            self.provider.calculate_premium(
                {
                    "sum_insured": float(body.sum_insured),
                    "capacity": float(body.capacity),
                    "tonnage": float(body.tonnage),
                    "cover_period": body.cover_period_used or body.cover_period,
                    "product": body.product_external_id,
                    "cover_option": body.cover_option_id,
                    "transaction_type": "1",
                }
            ),
        )
        await self.jobs.add_event(
            job,
            "EXTERNAL_RESPONSE_RECEIVED",
            message="checkPolicy+checkDoubleInsurance+calculatePremium",
        )
        if isinstance(policy_check, dict) and policy_check.get("exists") is True:
            expiry = (
                policy_check.get("ExpiryDate")
                or policy_check.get("expiryDate")
                or policy_check.get("Expiry")
            )
            detail = ""
            if expiry:
                detail = f" Current cover runs until {expiry}."
            raise ValidationAppError(
                "This vehicle is already covered under an active policy. "
                "To obtain a new quote, set the cover start date after the current "
                f"policy’s expiry.{detail}"
            )

        settings = get_settings()
        verdict = _evaluate_double_insurance(double)
        double_clear = _is_double_insurance_clear(double, settings=settings)
        if not double_clear and _should_enforce_double_insurance(settings):
            await self.jobs.transition(
                job,
                JobStatus.FAILED,
                error_code=(
                    "DOUBLE_INSURANCE_DETECTED"
                    if verdict == "DETECTED"
                    else "DOUBLE_INSURANCE_UNVERIFIED"
                ),
            )
            if verdict == "DETECTED":
                raise ValidationAppError("Double insurance was detected for this vehicle")
            raise ValidationAppError(
                "We could not confirm this vehicle is free of other cover. "
                "Please try again shortly."
            )
        if not double_clear:
            # UAT/dev: still call Definite, but allow reuse of test plates/chassis
            await self.jobs.add_event(
                job,
                "DOUBLE_INSURANCE_BYPASSED",
                message="Double insurance soft-check bypassed for non-LIVE environment",
                metadata={
                    "verdict": verdict,
                    "provider": double if isinstance(double, dict) else {},
                },
            )

        gross = _dec(premium.get("gross_premium"))
        if gross is None:
            raise ValidationAppError("Insurance provider did not return a gross premium")

        effective_period = str(
            premium.get("cover_period_used")
            or body.cover_period_used
            or body.cover_period
        )
        client_oid = resolve_proposal_client(is_guest=self.ctx.is_guest, customer=customer)
        if self.ctx.is_guest and not client_oid:
            raise ValidationAppError(
                "Insurer client is not linked. Return to client details and continue."
            )
        configured_agent = require_configured_definite_agent()
        # Bind the configured Definite agent for everyone except platform admins.
        if self.ctx.is_platform_admin and (body.agent_code or "").strip():
            agent_code = body.agent_code.strip()
        else:
            agent_code = configured_agent
        if not body.vehicle_model_code:
            raise ValidationAppError("Vehicle model is required for the certificate")
        if body.capacity is None or Decimal(body.capacity) <= 0:
            raise ValidationAppError("Seating capacity must be greater than zero")
        # Definite validates commencement in East Africa time — UTC wall-clock
        # can look like "yesterday" after midnight EAT and fail generateCertificate.
        commence = datetime.now(_NAIROBI).replace(microsecond=0, tzinfo=None)
        if body.cover_start_date and body.cover_start_date > date.today():
            commence = datetime.combine(body.cover_start_date, commence.time())
        make_name = body.vehicle_make_name.strip().upper()
        model_name = (body.vehicle_model_name or "").strip().upper()
        sum_insured_int = int(round(float(body.sum_insured or 0)))
        capacity_int = int(round(float(body.capacity)))
        tonnage_int = int(round(float(body.tonnage)))
        engine_number = (body.engine_number or "").strip().upper() or None
        provider_payload = {
            "agent": _as_int_or_str(agent_code),
            "CommencementDate": commence.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "PaymentInterval": _payment_interval(effective_period),
            "Product": _as_int_or_str(body.product_external_id),
            "CoverOption": _as_int_or_str(body.cover_option_id),
            "Registration": registration,
            # MakeOID/ModelOID from Definite catalog — these drive the certificate make/model
            "MakeCode": _as_int_or_str(body.vehicle_make_code),
            "ModelCode": _as_int_or_str(body.vehicle_model_code),
            # Names help Definite/DMVIC templates that read text fields
            "Make": make_name,
            "Model": model_name,
            "Capacity": capacity_int,
            "YOM": body.vehicle_year,
            "SumInsured": sum_insured_int,
            "ChassisNumber": body.chassis_number.strip().upper(),
            "EngineNumber": engine_number or "",
            "EngineRating": int(body.engine_rating or 1500),
            "ClientID": customer.id_number,
            "Tonnage": tonnage_int,
        }
        if client_oid is not None:
            holder = _as_int_or_str(client_oid)
            provider_payload["Client"] = holder
            provider_payload["PolicyHolder"] = holder
            provider_payload["ClientOID"] = holder
        if intermediary_name:
            provider_payload["Intermediary"] = intermediary_name
        if ira_number:
            provider_payload["IRA"] = ira_number
            provider_payload["IRANumber"] = ira_number

        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="newProposal")
        try:
            remote = await self.provider.create_proposal(provider_payload)
        except Exception:
            if idem_record is not None:
                await IdempotencyService(self.session).fail(idem_record)
            raise
        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="newProposal")
        remote_details = _proposal_details(remote)
        branch_id = await resolve_authorized_branch(
            self.ctx, self.session, getattr(customer, "branch_id", None)
        )

        proposal = Proposal(
            tenant_id=self.ctx.tenant_id,
            customer_id=customer.id,
            branch_id=branch_id,
            created_by_user_id=self.ctx.actor_user_id,
            product_code=body.product_code.strip().upper(),
            cover_option=(body.cover_option_name or body.cover_option_id).strip(),
            cover_period=effective_period.strip(),
            transaction_type="NEW",
            vehicle_registration=registration,
            vehicle_make=body.vehicle_make_name.strip().upper(),
            vehicle_model=(body.vehicle_model_name or body.vehicle_model_code or "").strip() or None,
            vehicle_year=body.vehicle_year,
            chassis_number=body.chassis_number.strip().upper(),
            engine_number=engine_number,
            engine_rating=int(body.engine_rating or 1500),
            make_code=str(body.vehicle_make_code).strip(),
            model_code=str(body.vehicle_model_code).strip(),
            agent_code=str(agent_code),
            referral_code=referral_code,
            intermediary_id=intermediary.id if intermediary else None,
            intermediary_name=intermediary_name,
            ira_number=ira_number,
            sum_insured=body.sum_insured,
            capacity=body.capacity,
            tonnage=body.tonnage,
            basic_premium=_dec(premium.get("basic_premium")),
            phcf=_dec(premium.get("phcf")),
            training_levy=_dec(premium.get("training_levy")),
            stamp_duty=_dec(premium.get("stamp_duty")),
            gross_premium=gross,
            status=ProposalStatus.APPROVED.value,
            double_insurance_clear=double_clear if double_clear else (
                False if _should_enforce_double_insurance(settings) else True
            ),
            double_insurance_result={
                **(double if isinstance(double, dict) else {"data": double}),
                "_enforced": _should_enforce_double_insurance(settings),
                "_bypassed_for_uat": (not double_clear)
                and not _should_enforce_double_insurance(settings),
            },
            policy_check_result=policy_check if isinstance(policy_check, dict) else {},
            external_proposal_ref=str(
                remote_details.get("OID")
                or remote_details.get("proposalId")
                or remote.get("proposalId")
                or uuid4().hex[:10]
            ),
            provider_note_oid=as_optional_str(
                remote_details.get("Note") or remote_details.get("noteOID")
            ),
            provider_insured_item=as_optional_str(remote_details.get("InsuredItem")),
            provider_document_number=as_optional_str(remote_details.get("DocumentNumber")),
            provider_amount_to_pay=as_optional_decimal(
                remote_details.get("AmountToPay")
            )
            or gross,
            provider_request_payload=provider_payload,
            provider_response_payload=remote if isinstance(remote, dict) else {"data": remote},
            cover_start_date=commence.date(),
            cover_end_date=commence.date() + timedelta(days=_cover_days(effective_period)),
            approved_at=datetime.now(UTC),
            approved_by_user_id=self.ctx.actor_user_id,
            submitted_at=datetime.now(UTC),
            job_id=job.job_key,
            correlation_id=job.job_key,
            request_id=as_optional_str(getattr(job, "request_id", None)),
            notes=None,
            channel="GUEST" if self.ctx.is_guest else "STAFF",
        )
        await self.proposals.add(proposal)
        await self.session.flush()

        note_oid = as_optional_str(remote_details.get("Note") or remote_details.get("noteOID"))
        insured_item = as_optional_str(remote_details.get("InsuredItem"))
        document_number = as_optional_str(remote_details.get("DocumentNumber"))
        amount_to_pay = as_optional_decimal(remote_details.get("AmountToPay")) or gross
        if amount_to_pay != gross:
            # Charge what Definite will settle against, not our quote.
            await self.jobs.add_event(
                job,
                "PROVIDER_AMOUNT_DIFFERS",
                message="Definite AmountToPay differs from quoted gross",
                metadata={"quoted_gross": str(gross), "amount_to_pay": str(amount_to_pay)},
            )
            gross = amount_to_pay
        commencement_at = parse_provider_datetime(remote_details.get("CommencementDate"))
        expiry_at = parse_provider_datetime(remote_details.get("ExpiryDate"))

        policy_number = f"POL-{uuid4().hex[:10].upper()}"
        policy = Policy(
            tenant_id=self.ctx.tenant_id,
            customer_id=customer.id,
            proposal_id=proposal.id,
            branch_id=branch_id,
            created_by_user_id=self.ctx.actor_user_id,
            policy_number=policy_number,
            product_code=proposal.product_code,
            cover_option=proposal.cover_option,
            vehicle_registration=registration,
            vehicle_make=proposal.vehicle_make,
            vehicle_model=proposal.vehicle_model,
            chassis_number=proposal.chassis_number,
            engine_number=proposal.engine_number,
            engine_rating=proposal.engine_rating,
            make_code=proposal.make_code,
            model_code=proposal.model_code,
            agent_code=proposal.agent_code,
            referral_code=proposal.referral_code,
            intermediary_id=proposal.intermediary_id,
            intermediary_name=proposal.intermediary_name,
            ira_number=proposal.ira_number,
            status=PolicyStatus.PENDING_PAYMENT.value,
            channel="GUEST" if self.ctx.is_guest else "STAFF",
            gross_premium=gross,
            sum_insured=body.sum_insured,
            cover_start_date=proposal.cover_start_date,
            cover_end_date=proposal.cover_end_date,
            external_policy_ref=str(
                remote_details.get("OID") or proposal.external_proposal_ref or ""
            ),
            provider_note_oid=note_oid,
            provider_insured_item=insured_item,
            provider_document_number=document_number,
            provider_amount_to_pay=amount_to_pay,
            provider_commencement_at=commencement_at,
            provider_expiry_at=expiry_at,
            provider_payload_summary={
                "proposal": remote if isinstance(remote, dict) else {"data": remote},
                "note_oid": note_oid,
                "insured_item": insured_item,
                "document_number": document_number,
                "amount_to_pay": float(amount_to_pay) if amount_to_pay is not None else float(gross),
                "proposal_oid": remote_details.get("OID"),
                "definite_client_oid": as_optional_int(client_oid),
                "commencement_date": remote_details.get("CommencementDate"),
                "expiry_date": remote_details.get("ExpiryDate"),
                "date_done": remote_details.get("DateDone"),
                "narration": remote_details.get("Narration"),
                "submitted": {
                    "make_code": str(body.vehicle_make_code),
                    "make_name": make_name,
                    "model_code": str(body.vehicle_model_code),
                    "model_name": model_name,
                    "sum_insured": sum_insured_int,
                    "agent_code": str(agent_code),
                    "intermediary_name": intermediary_name,
                    "ira_number": ira_number,
                    "chassis_number": proposal.chassis_number,
                    "engine_number": proposal.engine_number,
                    "engine_rating": proposal.engine_rating,
                    "capacity": capacity_int,
                    "tonnage": tonnage_int,
                    "yom": body.vehicle_year,
                    "client_id_number": customer.id_number,
                    "cover_period": effective_period,
                    "product_external_id": str(body.product_external_id),
                    "cover_option_id": str(body.cover_option_id),
                },
                "customer": {
                    "id": str(customer.id),
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "id_number": customer.id_number,
                    "phone": customer.phone,
                    "email": customer.email,
                    "external_client_ref": customer.external_client_ref,
                },
            },
            job_id=job.job_key,
            correlation_id=job.job_key,
            request_id=as_optional_str(getattr(job, "request_id", None)),
        )
        await self.policies.add(policy)
        proposal.status = ProposalStatus.CONVERTED.value
        proposal.version += 1

        # Keep customer record current with latest issuance linkage
        customer.last_issuance_job_id = job.job_key
        existing_payload = (
            dict(customer.provider_payload)
            if isinstance(getattr(customer, "provider_payload", None), dict)
            else {}
        )
        customer.provider_payload = {
            **existing_payload,
            "last_submit": {
                "job_id": job.job_key,
                "policy_id": str(policy.id),
                "proposal_id": str(proposal.id),
                "document_number": document_number,
                "note_oid": note_oid,
                "proposal_oid": as_optional_str(remote_details.get("OID")),
                "registration": registration,
            },
        }
        await self.session.flush()
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="issuance.submit",
            resource="policy",
            resource_id=str(policy.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "proposal_id": str(proposal.id),
                "registration": registration,
                "gross_premium": str(gross),
            },
        )
        result = {
            "job_id": job.job_key,
            "premium": premium,
            "proposal": proposal_to_public(proposal),
            "policy": policy_to_public(policy),
            "provider": {
                "proposal_oid": proposal.external_proposal_ref,
                "note_oid": remote_details.get("Note") or remote_details.get("noteOID"),
                "insured_item": remote_details.get("InsuredItem"),
                "document_number": remote_details.get("DocumentNumber"),
                "amount_to_pay": remote_details.get("AmountToPay") or float(gross),
            },
            "referral": await self._referral_summary(policy, customer),
            "reused": False,
        }
        if idem_record is not None:
            await IdempotencyService(self.session).complete(
                idem_record, response_body=result, job_id=job.job_key
            )
        return result

    async def _reuse_guest_issuance(
        self,
        *,
        customer_id: UUID,
        registration: str,
        product_code: str,
        terms: tuple[str, str, str, str],
    ) -> dict[str, Any] | None:
        candidates = await self.policies.find_unpaid_for_customer_vehicle(
            customer_id=customer_id,
            registration=registration,
            product_code=product_code,
        )
        policy = None
        proposal = None
        for candidate in candidates:
            if candidate.proposal_id is None:
                continue
            from app.core.exceptions import ResourceNotFoundError

            candidate_proposal = None
            with contextlib.suppress(ResourceNotFoundError):
                candidate_proposal = await self.proposals.get(candidate.proposal_id)
            if candidate_proposal is None:
                continue
            sent = candidate_proposal.provider_request_payload or {}
            if not isinstance(sent, dict):
                continue
            sent_terms = _quote_terms(
                cover_option_id=sent.get("CoverOption"),
                period=sent.get("PaymentInterval"),
                capacity=sent.get("Capacity"),
                sum_insured=sent.get("SumInsured"),
            )
            if sent_terms == terms:
                policy, proposal = candidate, candidate_proposal
                break
        if policy is None:
            return None
        try:
            customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                customer_id
            )
        except Exception:
            customer = None
        return {
            "referral": await self._referral_summary(policy, customer),
            "job_id": policy.job_id,
            "premium": {
                "gross_premium": float(policy.gross_premium) if policy.gross_premium else None
            },
            "proposal": proposal_to_public(proposal) if proposal is not None else None,
            "policy": policy_to_public(policy),
            "provider": {
                "proposal_oid": policy.external_policy_ref,
                "note_oid": policy.provider_note_oid,
                "insured_item": policy.provider_insured_item,
                "document_number": policy.provider_document_number,
                "amount_to_pay": (
                    float(policy.provider_amount_to_pay)
                    if policy.provider_amount_to_pay is not None
                    else None
                ),
            },
            "reused": True,
        }

    async def _payable_policy(self, policy_id: str) -> Policy:
        policy = await self.policies.get(UUID(policy_id))
        if policy.customer_id is not None:
            from app.modules.guest.ownership import require_owned_customer_ctx

            owner = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                policy.customer_id
            )
            require_owned_customer_ctx(self.ctx, owner)
        elif self.ctx.is_guest:
            from app.core.exceptions import AuthorizationError
            from app.modules.guest.ownership import GUEST_RESOURCE_ERROR

            raise AuthorizationError(GUEST_RESOURCE_ERROR)
        return policy

    async def cancel_pending_payment(self, policy_id: str) -> dict[str, Any]:
        """Abandon an unconfirmed STK so the next pay sends a fresh prompt.

        A late success webhook for the abandoned prompt is still honoured
        (see ``PaymentService.apply_webhook``), so a customer who approves the
        old prompt is never charged without cover.
        """
        self.ctx.require_active_tenant()
        from app.modules.payments.repository import PaymentRepository

        policy = await self._payable_policy(policy_id)
        latest = await PaymentRepository(self.session, self.ctx).find_active_attempt_for_policy(
            policy.id
        )
        pending = {PaymentStatus.PENDING.value, PaymentStatus.INITIATED.value}
        if latest is None:
            return {"cancelled": False, "payment": None}
        payments = PaymentService(self.session, self.ctx, self.provider)
        latest = await payments.sync_definite_stk_confirmation(latest)
        if latest.status not in pending:
            return {"cancelled": False, "payment": payment_to_public(latest)}

        latest.status = PaymentStatus.CANCELLED.value
        latest.failure_code = USER_CANCELLED_PAYMENT
        latest.failure_message = "Cancelled before confirmation"
        latest.version += 1
        await self.session.flush()
        await self.audit.record(
            action="payment.user_cancelled",
            resource="payment",
            resource_id=str(latest.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={"policy_id": str(policy.id), "method": latest.method},
        )
        return {"cancelled": True, "payment": payment_to_public(latest)}

    async def pay(self, body: IssuancePayRequest) -> dict[str, Any]:
        """Pay step.

        Only the float-funded Definite wallet rail settles at pay time. Customer-funded
        rails (Definite M-Pesa, BirdView) stay PENDING until payment is confirmed, so no
        certificate is issued in the same request that sends the STK prompt.
        """
        self.ctx.require_active_tenant()
        from app.modules.system_config.service import SystemConfigService

        await SystemConfigService(self.session).require_service("payments")
        policy = await self._payable_policy(body.policy_id)
        if policy.gross_premium is None:
            raise ValidationAppError("Policy missing premium")

        plan = resolve_settlement_plan(body.method)
        method = plan.rail.value
        if self.ctx.is_guest and method not in GUEST_ALLOWED_RAILS:
            raise ValidationAppError("Guest payments must use BirdView M-Pesa")
        if plan.required_permission:
            self.ctx.require_permission(plan.required_permission)
        if plan.requires_phone and not (body.phone or "").strip():
            raise ValidationAppError(f"{plan.label} requires a phone number")

        payments = PaymentService(self.session, self.ctx, self.provider)
        payment_public: dict[str, Any]
        payment_status: str
        payment_id: str | None

        if policy.status == PolicyStatus.PENDING_PAYMENT.value:
            from app.modules.payments.repository import PaymentRepository

            pay_repo = PaymentRepository(self.session, self.ctx)
            # A late success on an abandoned prompt may not be the newest row.
            latest = await pay_repo.find_success_for_policy(
                policy.id
            ) or await pay_repo.find_latest_for_policy(policy.id)
            if latest and latest.status == PaymentStatus.SUCCESS.value:
                # BirdView webhook can mark the row SUCCESS a moment before the
                # policy leaves PENDING_PAYMENT. Never send a second STK.
                await payments._on_success(
                    latest,
                    policy_id=policy.id,
                    generate_certificate=False,
                )
                payment_public = payment_to_public(latest)
                payment_status = latest.status
                payment_id = str(latest.id)
                try:
                    plan = resolve_settlement_plan(str(latest.method))
                except ValidationAppError:
                    pass
            elif (
                latest
                and latest.method in ASYNC_STK_METHODS
                and latest.status in {"PENDING", "INITIATED"}
            ):
                # Already prompted once. Definite M-Pesa may already be approved
                # on the insurer side even though the local row is still PENDING.
                latest = await payments.sync_definite_stk_confirmation(latest)
                payment_public = payment_to_public(latest)
                payment_status = latest.status
                payment_id = str(latest.id)
            else:
                # New STK / Definite settle only when none pending (first pay or after FAILED)
                retry_suffix = (
                    f"-r{latest.id}" if latest and latest.status in {"FAILED", "CANCELLED"} else ""
                )
                payment = await payments.initiate(
                    PaymentInitiateRequest(
                        policy_id=policy.id,
                        method=method,
                        phone=body.phone,
                    ),
                    idempotency_key=f"issue-pay-{policy.id}{retry_suffix}",
                    # Cert path owns generateCertificate (and BirdView→wallet settle)
                    generate_certificate=False,
                )
                if isinstance(payment, dict):
                    payment_public = payment
                    payment_status = str(payment.get("status"))
                    payment_id = payment.get("id")
                else:
                    payment_public = payment_to_public(payment)
                    payment_status = payment.status
                    payment_id = str(payment.id)
        elif policy.status in {
            PolicyStatus.ACTIVE.value,
            PolicyStatus.PENDING_CERTIFICATE.value,
        }:
            # Local payment already succeeded; only finish Definite certificate once
            from app.modules.payments.repository import PaymentRepository

            matched = await PaymentRepository(self.session, self.ctx).find_latest_for_policy(
                policy.id, status="SUCCESS"
            )
            if matched is None:
                raise ValidationAppError("Payment succeeded but payment record was not found")
            payment_public = payment_to_public(matched)
            payment_status = matched.status
            payment_id = str(matched.id)
            try:
                plan = resolve_settlement_plan(str(matched.method))
            except ValidationAppError:
                pass
        else:
            raise ValidationAppError("Policy is not awaiting payment")

        certificate = None
        if payment_status == "SUCCESS" and payment_id:
            from app.modules.certificates.repository import CertificateRepository
            from app.modules.payments.enums import CertificateStatus

            policy = await self.policies.get(policy.id)
            row = await CertificateRepository(self.session, self.ctx).find_by_policy(policy.id)
            if row and row.status == CertificateStatus.GENERATED.value:
                # Cert already issued — PDF may still be warming; download endpoint polls Azure
                certificate = cert_to_public(row)
            else:
                # Idempotent: Definite settle once (no-op if already done at pay), then cert.
                cert = await CertificateService(
                    self.session, self.ctx, self.provider
                ).generate_for_policy(
                    policy.id,
                    payment_id=UUID(str(payment_id)),
                    approve_provider_note=True,
                    definite_payment_method=int(plan.definite_payment_method),
                )
                certificate = cert_to_public(cert)

        policy = await self.policies.get(policy.id)
        return {
            "payment": payment_public,
            "policy": policy_to_public(policy),
            "certificate": certificate,
        }


def _as_int_or_str(value: str | int | None) -> int | str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return text


def _payment_interval(cover_period: str) -> str:
    """newProposal PaymentInterval — same vocabulary Definite prices with."""
    from app.integrations.insurance.definite_assurance.service import definite_cover_period

    return definite_cover_period(cover_period)


def _cover_days(cover_period: str) -> int:
    normalized = cover_period.strip().lower()
    if "month" in normalized and "semi" not in normalized:
        return 30
    if "quarter" in normalized:
        return 90
    if "semi" in normalized or "install" in normalized:
        return 180
    return 365


def _proposal_details(remote: Any) -> dict[str, Any]:
    if not isinstance(remote, dict):
        return {}
    details = remote.get("proposalDetails")
    if isinstance(details, dict):
        return details
    data = remote.get("data")
    if isinstance(data, dict) and isinstance(data.get("proposalDetails"), dict):
        return data["proposalDetails"]
    return remote
