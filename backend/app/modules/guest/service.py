"""Guest-plane facade — the only service guests may invoke.

Internally reuses issuance/payment/certificate implementations so the
welcome-screen quote journey stays intact. Those internals receive a
guest execution adapter with empty staff permissions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.enums import JobStatus, JobType
from app.core.database.redis_client import get_redis_client
from app.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationAppError
from app.core.security.guest_capabilities import GuestContext
from app.core.validation.identity import (
    id_number_compact,
    id_number_lookup_variants,
    normalize_id_number,
    normalize_kra_pin,
    normalize_phone,
)
from app.integrations.insurance.ports import InsuranceProvider
from app.modules.audit.service import AuditService
from app.modules.certificates.access_enums import CertificateAccessKind
from app.modules.certificates.service import CertificateService
from app.modules.customers.enums import CustomerOrigin
from app.modules.customers.models import Customer
from app.modules.customers.repository import CustomerRepository
from app.modules.guest.insurance_gateway import GuestInsuranceGateway
from app.modules.guest.ownership import (
    GUEST_IDENTITY_ERROR,
    GUEST_RESOURCE_ERROR,
    require_owned_customer,
)
from app.modules.insurance.issuance_schemas import (
    IssuanceClientRequest,
    IssuancePayRequest,
    IssuanceSubmitRequest,
)
from app.modules.insurance.issuance_service import IssuanceService
from app.modules.insurance.guest_session import (
    bind_guest_customer,
    bind_guest_policy,
    enforce_guest_identity_lookup_limit,
)
from app.modules.insurance.schemas import PremiumCalculateRequest
from app.modules.insurance.service import InsuranceOrchestrationService
from app.modules.jobs.service import JobService
from app.modules.payments.service import PaymentService
from app.modules.policies.repository import PolicyRepository
from app.modules.products.cache import ReferenceDataCache


GUEST_RETURNING_INCOMPLETE = (
    "We couldn't load your saved details. Please enter them manually."
)

def _mask_name(value: str | None) -> str:
    cleaned = (value or "").strip()
    return f"{cleaned[0].upper()}***" if cleaned else ""


def _mask_tail(value: str | None, *, keep_start: int = 0, keep_end: int = 3) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= keep_start + keep_end:
        return "*" * len(cleaned)
    hidden = len(cleaned) - keep_start - keep_end
    return f"{cleaned[:keep_start]}{'*' * hidden}{cleaned[len(cleaned) - keep_end:]}"


def _mask_email(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if "@" not in cleaned:
        return None
    local, _, domain = cleaned.partition("@")
    return f"{local[:1]}***@{domain}"


def _masked_vehicle(proposal) -> dict[str, Any]:
    return {
        "registration": _mask_tail(proposal.vehicle_registration, keep_start=3, keep_end=1),
        "chassis_number": _mask_tail(proposal.chassis_number, keep_end=4),
        "engine_number": _mask_tail(proposal.engine_number, keep_end=3),
        "vehicle_year": proposal.vehicle_year,
        "engine_rating": proposal.engine_rating,
        "make_code": proposal.make_code,
        "make_name": proposal.vehicle_make,
        "model_code": proposal.model_code,
        "model_name": proposal.vehicle_model,
    }


class GuestService:
    def __init__(
        self,
        session: AsyncSession,
        guest: GuestContext,
        provider: InsuranceProvider,
        request: Request,
    ) -> None:
        self.session = session
        self.guest = guest
        self.provider = (
            provider
            if isinstance(provider, GuestInsuranceGateway)
            else GuestInsuranceGateway(provider)
        )
        self.request = request
        self.ctx = guest.as_execution_context()
        self.cache = ReferenceDataCache(get_redis_client())
        self.customers = CustomerRepository(session, self.ctx)
        self.policies = PolicyRepository(session, self.ctx)
        self.jobs = JobService(session, self.ctx)
        self.audit = AuditService(session)

    def _issuance(self) -> IssuanceService:
        return IssuanceService(self.session, self.ctx, self.provider, self.cache)

    def _orchestration(self) -> InsuranceOrchestrationService:
        return InsuranceOrchestrationService(
            self.session, self.ctx, self.provider, self.cache
        )

    def _guest_client_view(self, customer: Customer, body: IssuanceClientRequest) -> dict[str, Any]:
        return {
            "id": str(customer.id),
            "first_name": body.first_name,
            "last_name": body.last_name,
            "other_names": body.other_names,
            "id_number": normalize_id_number(body.id_number),
            "phone": normalize_phone(body.phone or "") or None,
            "email": body.email,
            "kra_pin": None,
            "external_client_ref": None,
            "status": customer.status,
        }

    async def _require_owned_customer(self, customer_id: UUID) -> Customer:
        try:
            customer = await self.customers.get_active_by_id(customer_id)
        except ResourceNotFoundError as exc:
            raise AuthorizationError(GUEST_RESOURCE_ERROR) from exc
        require_owned_customer(customer, self.guest)
        return customer

    async def _require_owned_policy(self, policy_id: UUID):
        try:
            policy = await self.policies.get(policy_id)
        except ResourceNotFoundError as exc:
            raise AuthorizationError(GUEST_RESOURCE_ERROR) from exc
        if policy.customer_id is None:
            raise AuthorizationError(GUEST_RESOURCE_ERROR)
        await self._require_owned_customer(policy.customer_id)
        return policy

    async def get_catalog(self) -> dict[str, Any]:
        return await self._orchestration().get_catalog()

    async def calculate_premium(self, body: PremiumCalculateRequest) -> dict[str, Any]:
        result = await self.provider.calculate_premium(
            {
                "sum_insured": body.sum_insured,
                "capacity": body.capacity,
                "tonnage": body.tonnage,
                "cover_period": body.cover_period,
                "product": body.product,
                "cover_option": body.cover_option,
                "transaction_type": body.transaction_type,
            }
        )
        await self.audit.record(
            action="insurance.guest_premium_calculate",
            resource="premium",
            resource_id=None,
            tenant_id=self.guest.tenant_id,
            user_id=None,
            metadata={
                "product": body.product,
                "cover_option": body.cover_option,
                "gross_premium": result.get("gross_premium") if isinstance(result, dict) else None,
                "channel": "GUEST",
            },
        )
        return {"job_id": None, "premium": result}

    async def _lookup_definite_client(self, id_number: str) -> dict[str, Any] | None:
        """Fail closed for create: provider errors / unreadable lookups are not 'new'.

        Tries hyphenated and compact ID forms — Definite may store passports either way.
        """
        saw_clear_absent = False
        saw_error = False
        for candidate in id_number_lookup_variants(id_number):
            try:
                found = await self.provider.check_client(id_number=candidate)
            except Exception:
                saw_error = True
                continue
            if found is not None:
                return found
            saw_clear_absent = True
        if saw_clear_absent:
            return None
        if saw_error:
            raise ValidationAppError(GUEST_IDENTITY_ERROR) from None
        return None

    async def _bind_session_guest_with_insurer_ref(
        self,
        *,
        normalized: str,
        remote_ref: str,
        first_name: str,
        last_name: str,
        other_names: str | None,
        kra_pin: str | None,
        phone: str | None,
        email: str | None,
        audit_action: str,
        provider_payload: dict[str, Any] | None = None,
        masked: bool = False,
        view_body: IssuanceClientRequest | None = None,
    ) -> dict[str, Any]:
        """Session-owned guest row bound to an insurer OID (no createClient)."""
        from app.core.security.branch_scope import resolve_authorized_branch

        branch_id = await resolve_authorized_branch(self.ctx, self.session, None)
        customer = Customer(
            tenant_id=self.guest.tenant_id,
            origin=CustomerOrigin.GUEST.value,
            guest_session_id=self.guest.session_id,
            branch_id=branch_id,
            created_by_user_id=None,
            assigned_user_id=None,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            other_names=other_names.strip() if other_names else None,
            id_number=normalized,
            kra_pin=kra_pin,
            phone=phone,
            email=(str(email).lower() if email else None),
            status="ACTIVE",
            external_client_ref=remote_ref,
            provider_payload=provider_payload or {},
        )
        try:
            async with self.session.begin_nested():
                await self.customers.add(customer)
                await self.session.flush()
        except IntegrityError:
            raced = await self.customers.find_guest_by_session_id_number(
                normalized, self.guest.session_id
            )
            if raced is None:
                raise ValidationAppError(GUEST_IDENTITY_ERROR) from None
            customer = raced
            # Same session already has this ID (retry / second vehicle). Heal OID.
            existing_ref = str(getattr(customer, "external_client_ref", None) or "").strip()
            if remote_ref and existing_ref != remote_ref:
                if not existing_ref or existing_ref == normalized:
                    customer.external_client_ref = remote_ref
                    await self.session.flush()

        from app.modules.referrals.service import ReferralService

        await ReferralService(self.session).ensure_code_for_customer(customer)
        await self.audit.record(
            action=audit_action,
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.guest.tenant_id,
            user_id=None,
            metadata={
                "origin": CustomerOrigin.GUEST.value,
                **(provider_payload or {}),
            },
        )
        await bind_guest_customer(self.request, customer.id)
        if masked:
            local = self._masked_client_view(customer)
        else:
            if view_body is None:
                raise ValidationAppError(GUEST_IDENTITY_ERROR)
            local = self._guest_client_view(customer, view_body)
        return {"job_id": None, "provider": {}, "local": local}

    async def _assert_guest_created_definite_identity(self, customer: Customer) -> None:
        """Resume/submit may continue for a session-owned guest client.

        Guests never pick a ClientOID from the request. We only continue when:
        - Definite has no person yet (new ID), or
        - this session-owned row already holds the matching insurer OID, or
        - Definite has the person and we can heal a missing/stale OID onto this
          session row (same client, another vehicle).

        Staff CRM rows are never used here; callers pass session-owned guests only.
        When the insurer lookup is flaky but we already hold a bound OID, allow resume.
        """
        idn = normalize_id_number(customer.id_number)
        stored = str(getattr(customer, "external_client_ref", None) or "").strip()
        try:
            remote = await self._lookup_definite_client(idn)
        except ValidationAppError:
            if stored:
                return
            raise
        if remote is None:
            return
        found = str((remote or {}).get("external_ref") or "").strip()
        if stored and found and stored == found:
            return

        # Prefer a real insurer OID over a mapper fallback that is just the ID number.
        preferred = found
        if stored and stored != idn and (not found or found == idn):
            preferred = stored
        if not preferred or preferred == idn:
            raise ValidationAppError(GUEST_IDENTITY_ERROR)
        if preferred != stored:
            customer.external_client_ref = preferred
            await self.session.flush()

    async def _returning_source(self, id_number: str) -> Customer | None:
        from sqlalchemy import func, or_, select

        compact = id_number_compact(id_number)
        return await self.session.scalar(
            select(Customer)
            .where(
                Customer.tenant_id == self.guest.tenant_id,
                Customer.deleted_at.is_(None),
                or_(
                    Customer.id_number == id_number,
                    func.replace(Customer.id_number, "-", "") == compact,
                ),
            )
            .order_by(Customer.updated_at.desc())
            .limit(1)
        )

    async def _returning_vehicle(self, id_number: str):
        from sqlalchemy import func, or_, select

        from app.modules.proposals.models import Proposal

        compact = id_number_compact(id_number)
        return await self.session.scalar(
            select(Proposal)
            .join(Customer, Customer.id == Proposal.customer_id)
            .where(
                Proposal.tenant_id == self.guest.tenant_id,
                Customer.tenant_id == self.guest.tenant_id,
                Customer.deleted_at.is_(None),
                or_(
                    Customer.id_number == id_number,
                    func.replace(Customer.id_number, "-", "") == compact,
                ),
            )
            .order_by(Proposal.created_at.desc())
            .limit(1)
        )

    def _masked_client_view(self, customer: Customer) -> dict[str, Any]:
        return {
            "id": str(customer.id),
            "first_name": _mask_name(customer.first_name),
            "last_name": _mask_name(customer.last_name),
            "other_names": None,
            "id_number": customer.id_number,
            "phone": _mask_tail(customer.phone, keep_start=5, keep_end=3),
            "email": _mask_email(customer.email),
            "kra_pin": None,
            "external_client_ref": None,
            "status": customer.status,
        }

    async def lookup_returning_client(self, id_number: str) -> dict[str, Any]:
        """Masked prefill for a returning guest.

        An ID number is not proof of identity, so only masked values leave this
        endpoint; the real stored values are applied server-side on save/submit.
        """
        await enforce_guest_identity_lookup_limit(self.request)
        normalized = normalize_id_number(id_number)
        row = await self._returning_source(normalized)
        if row is None:
            return {"found": False, "masked_name": None, "client": None, "vehicle": None}
        client = self._masked_client_view(row)
        vehicle = await self._returning_vehicle(normalized)
        return {
            "found": True,
            "masked_name": " ".join(
                part for part in (client["first_name"], client["last_name"]) if part
            )
            or None,
            "client": {
                "first_name": client["first_name"],
                "last_name": client["last_name"],
                "phone": client["phone"],
                "email": client["email"],
            },
            "vehicle": _masked_vehicle(vehicle) if vehicle is not None else None,
        }

    async def _continue_returning_client(
        self, normalized: str, source: Customer
    ) -> dict[str, Any]:
        """Bind a session guest row from a prior agency record (no createClient dupes)."""
        source_ref = str(getattr(source, "external_client_ref", None) or "").strip()
        try:
            remote = await self._lookup_definite_client(normalized)
        except ValidationAppError:
            # Agency already knows this client; passport checkClient can be unreadable.
            if not source_ref:
                raise
            remote = {"external_ref": source_ref}

        if remote is None:
            from pydantic import ValidationError

            try:
                body = IssuanceClientRequest(
                    first_name=source.first_name,
                    last_name=source.last_name,
                    other_names=source.other_names,
                    id_number=normalized,
                    phone=source.phone,
                    kra_pin=source.kra_pin,
                    email=source.email,
                )
            except ValidationError:
                raise ValidationAppError(GUEST_RETURNING_INCOMPLETE) from None
            data = await self._create_guest_client(body)
            customer = await self._require_owned_customer(UUID(data["local"]["id"]))
            return {**data, "local": self._masked_client_view(customer)}

        remote_ref = str(remote.get("external_ref") or "").strip() or source_ref
        if not remote_ref:
            raise ValidationAppError(GUEST_IDENTITY_ERROR)

        return await self._bind_session_guest_with_insurer_ref(
            normalized=normalized,
            remote_ref=remote_ref,
            first_name=source.first_name,
            last_name=source.last_name,
            other_names=source.other_names,
            kra_pin=source.kra_pin,
            phone=source.phone,
            email=source.email,
            audit_action="insurance.guest_client_returning",
            provider_payload={"returning_source": str(source.id)},
            masked=True,
        )

    async def ensure_returning_client(self, id_number: str) -> dict[str, Any]:
        """Start a guest quote from a returning client's stored details.

        Creates a session-owned guest row from the stored record so the guest
        never sees (or retypes) the real values. The response stays masked.
        """
        await enforce_guest_identity_lookup_limit(self.request)
        normalized = normalize_id_number(id_number)
        existing = await self.customers.find_guest_by_session_id_number(
            normalized, self.guest.session_id
        )
        if existing is not None:
            await self._assert_guest_created_definite_identity(existing)
            await bind_guest_customer(self.request, existing.id)
            return {"job_id": None, "provider": {}, "local": self._masked_client_view(existing)}

        source = await self._returning_source(normalized)
        if source is None:
            raise ValidationAppError(GUEST_RETURNING_INCOMPLETE)
        return await self._continue_returning_client(normalized, source)

    async def _create_guest_client(self, body: IssuanceClientRequest) -> dict[str, Any]:
        """Create at the insurer, or bind to an existing insurer OID for this session.

        A prior guest attempt can leave the ID at Definite with no usable local row.
        Blocking forever made passport / retry quotes impossible — bind a session-
        owned guest row to the insurer OID using the details the guest just entered.
        Never attaches to a staff CRM customer.
        """
        normalized = normalize_id_number(body.id_number)
        remote = await self._lookup_definite_client(normalized)
        if remote is not None:
            remote_ref = str(remote.get("external_ref") or "").strip()
            if not remote_ref:
                raise ValidationAppError(GUEST_IDENTITY_ERROR)
            return await self._bind_session_guest_with_insurer_ref(
                normalized=normalized,
                remote_ref=remote_ref,
                first_name=body.first_name,
                last_name=body.last_name,
                other_names=body.other_names,
                kra_pin=normalize_kra_pin(body.kra_pin),
                phone=normalize_phone(body.phone) or body.phone,
                email=str(body.email).lower(),
                audit_action="insurance.guest_client_insurer_bind",
                provider_payload={"insurer_bind": True},
                masked=False,
                view_body=body,
            )

        job = await self.jobs.create(
            tenant_id=self.guest.tenant_id,
            user_id=None,
            job_type=JobType.CLIENT_CREATION,
        )
        try:
            from app.core.security.branch_scope import resolve_authorized_branch

            await self.jobs.add_event(
                job,
                "EXTERNAL_RESPONSE_RECEIVED",
                metadata={"linked": False, "check": "absent"},
            )
            await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="createClient")
            created = await self.provider.create_client(
                {
                    "first_name": body.first_name,
                    "last_name": body.last_name,
                    "other_names": body.other_names,
                    "id_number": normalized,
                    "kra_pin": normalize_kra_pin(body.kra_pin),
                    "phone": normalize_phone(body.phone),
                    "email": str(body.email).lower(),
                }
            )
            created_ref = str((created or {}).get("external_ref") or "").strip() or None
            # Some createClient replies omit the OID; resolve it so a second vehicle
            # quote for the same client can bind ClientOID on newProposal.
            if not created_ref or created_ref == normalized:
                recheck = await self._lookup_definite_client(normalized)
                resolved = str((recheck or {}).get("external_ref") or "").strip()
                if resolved and resolved != normalized:
                    created_ref = resolved
            await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="createClient")
            branch_id = await resolve_authorized_branch(self.ctx, self.session, None)

            customer = Customer(
                tenant_id=self.guest.tenant_id,
                origin=CustomerOrigin.GUEST.value,
                guest_session_id=self.guest.session_id,
                branch_id=branch_id,
                created_by_user_id=None,
                assigned_user_id=None,
                first_name=body.first_name.strip(),
                last_name=body.last_name.strip(),
                other_names=body.other_names.strip() if body.other_names else None,
                id_number=normalized,
                kra_pin=normalize_kra_pin(body.kra_pin),
                phone=normalize_phone(body.phone) or body.phone,
                email=str(body.email).lower(),
                status="ACTIVE",
                # Prefer the OID returned by OUR createClient.
                external_client_ref=created_ref,
                provider_payload={},
                last_issuance_job_id=job.job_key,
            )
            async with self.session.begin_nested():
                await self.customers.add(customer)
                await self.session.flush()
        except IntegrityError:
            raced = await self.customers.find_guest_by_session_id_number(
                normalized, self.guest.session_id
            )
            if raced is None:
                raise ValidationAppError(GUEST_IDENTITY_ERROR) from None
            await self._assert_guest_created_definite_identity(raced)
            await bind_guest_customer(self.request, raced.id)
            return {
                "job_id": None,
                "provider": {},
                "local": self._guest_client_view(raced, body),
            }
        except Exception:
            await self.jobs.transition(job, JobStatus.FAILED, error_code="GUEST_IDENTITY")
            await self.audit.record(
                action="insurance.guest_client_ensure_denied",
                resource="customer",
                resource_id=None,
                tenant_id=self.guest.tenant_id,
                user_id=None,
                result="FAILURE",
                metadata={"reason": "guest_identity_unverified"},
            )
            raise ValidationAppError(GUEST_IDENTITY_ERROR) from None

        from app.modules.referrals.service import ReferralService

        await ReferralService(self.session).ensure_code_for_customer(customer)
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="insurance.guest_client_ensure",
            resource="customer",
            resource_id=str(customer.id),
            tenant_id=self.guest.tenant_id,
            user_id=None,
            metadata={"origin": CustomerOrigin.GUEST.value},
        )
        await bind_guest_customer(self.request, customer.id)
        return {
            "job_id": job.job_key,
            "provider": {},
            "local": self._guest_client_view(customer, body),
        }

    async def ensure_client(self, body: IssuanceClientRequest) -> dict[str, Any]:
        """Create or resume a guest-owned customer for this session only.

        Never attaches to a staff CRM row. ID number + phone are quote fields,
        not proof of ownership of an existing customer. When this agency already
        has a prior record for the ID, reuse that returning path instead of
        attempting createClient (which would fail as a duplicate at the insurer).
        """
        await enforce_guest_identity_lookup_limit(self.request)
        normalized = normalize_id_number(body.id_number)
        existing = await self.customers.find_guest_by_session_id_number(
            normalized, self.guest.session_id
        )
        if existing is not None:
            await self._assert_guest_created_definite_identity(existing)
            await bind_guest_customer(self.request, existing.id)
            return {
                "job_id": None,
                "provider": {},
                "local": self._guest_client_view(existing, body),
            }

        source = await self._returning_source(normalized)
        if source is not None:
            return await self._continue_returning_client(normalized, source)

        return await self._create_guest_client(body)

    async def submit(
        self, body: IssuanceSubmitRequest, *, use_last_vehicle: bool = False
    ) -> dict[str, Any]:
        from app.modules.insurance.guest_session import (
            enforce_guest_submit_limit,
            release_guest_submit_slot,
            reserve_guest_submit_slot,
        )

        customer = await self._require_owned_customer(UUID(body.customer_id))
        await self._assert_guest_created_definite_identity(customer)
        if use_last_vehicle:
            last = await self._returning_vehicle(normalize_id_number(customer.id_number))
            if last is None or not last.chassis_number:
                raise ValidationAppError(
                    "We couldn't load your saved vehicle. Please enter its details."
                )
            body = body.model_copy(
                update={
                    "vehicle_registration": last.vehicle_registration,
                    "chassis_number": last.chassis_number,
                    "engine_number": last.engine_number,
                }
            )
        await enforce_guest_submit_limit(self.request)
        await reserve_guest_submit_slot(self.request)
        try:
            data = await self._issuance().submit(body)
        except Exception:
            await release_guest_submit_slot(self.request)
            raise
        if data.get("reused"):
            await release_guest_submit_slot(self.request)
        policy = data.get("policy") or {}
        if policy.get("id"):
            await bind_guest_policy(self.request, UUID(str(policy["id"])))
        view = self._guest_issuance_view(data)
        if use_last_vehicle:
            for key in ("proposal", "policy"):
                record = view.get(key)
                if isinstance(record, dict):
                    record["vehicle_registration"] = _mask_tail(
                        record.get("vehicle_registration"), keep_start=3, keep_end=1
                    )
                    record["chassis_number"] = _mask_tail(record.get("chassis_number"), keep_end=4)
                    record["engine_number"] = _mask_tail(record.get("engine_number"), keep_end=3)
        return view

    def _guest_issuance_view(self, data: dict[str, Any]) -> dict[str, Any]:
        """Strip insurer object IDs and the configured agent from the guest plane."""
        proposal = dict(data.get("proposal") or {}) if isinstance(data.get("proposal"), dict) else data.get("proposal")
        policy = dict(data.get("policy") or {}) if isinstance(data.get("policy"), dict) else data.get("policy")
        if isinstance(proposal, dict):
            for key in (
                "agent_code",
                "external_proposal_ref",
                "provider_note_oid",
                "provider_insured_item",
            ):
                proposal.pop(key, None)
        if isinstance(policy, dict):
            for key in (
                "agent_code",
                "external_policy_ref",
                "provider_note_oid",
                "provider_insured_item",
                "provider_payment_txn",
            ):
                policy.pop(key, None)
        provider = data.get("provider") if isinstance(data.get("provider"), dict) else {}
        return {
            **data,
            "proposal": proposal,
            "policy": policy,
            "provider": {
                "document_number": provider.get("document_number"),
                "amount_to_pay": provider.get("amount_to_pay"),
            },
        }

    async def pay(self, body: IssuancePayRequest) -> dict[str, Any]:
        await self._require_owned_policy(UUID(body.policy_id))
        return self._guest_issuance_view(await self._issuance().pay(body))

    async def cancel_payment(self, policy_id: UUID) -> dict[str, Any]:
        await self._require_owned_policy(policy_id)
        return await self._issuance().cancel_pending_payment(str(policy_id))

    async def get_payment(self, payment_id: UUID):
        try:
            row = await PaymentService(self.session, self.ctx, self.provider).get(payment_id)
        except ResourceNotFoundError as exc:
            raise AuthorizationError(GUEST_RESOURCE_ERROR) from exc
        if row.policy_id is None:
            raise AuthorizationError(GUEST_RESOURCE_ERROR)
        await self._require_owned_policy(row.policy_id)
        return row

    async def download_certificate(
        self,
        certificate_id: UUID,
        *,
        access_kind: CertificateAccessKind,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[bytes, str]:
        service = CertificateService(self.session, self.ctx, self.provider)
        try:
            cert = await service.get(certificate_id)
        except ResourceNotFoundError as exc:
            raise AuthorizationError(GUEST_RESOURCE_ERROR) from exc
        if cert.policy_id is None:
            raise AuthorizationError(GUEST_RESOURCE_ERROR)
        await self._require_owned_policy(cert.policy_id)
        return await service.download_pdf(
            certificate_id,
            access_kind=access_kind,
            ip_address=ip_address,
            user_agent=user_agent,
        )
