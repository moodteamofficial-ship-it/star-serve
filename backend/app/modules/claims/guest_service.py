"""Guest FNOL and follow-up — capability session + identity proof, never staff RBAC."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.database.rls import set_rls_context
from app.core.exceptions import AuthorizationError, ConflictError, ValidationAppError
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.core.validation.identity import (
    normalize_id_number,
    normalize_phone,
    normalize_vehicle_registration,
)
from app.modules.certificates.models import Certificate
from app.modules.claims.enums import (
    ClaimChannel,
    ClaimEventActorType,
    ClaimStatus,
    ClaimType,
    FollowupStatus,
    FollowupType,
    NoteVisibility,
    TERMINAL_STATUSES,
)
from app.modules.claims.events import ClaimEventService
from app.modules.claims.guest_schemas import GuestClaimCreateRequest, GuestClaimLookupRequest
from app.modules.claims.models import Claim, ClaimFollowup, ClaimNote
from app.modules.customers.models import Customer
from app.modules.insurance.guest_session import (
    assert_guest_owns_claim,
    bind_guest_claim,
    bind_guest_customer,
    bind_guest_fnol_tenant,
    bind_guest_policy,
    guest_fnol_tenant_ids,
)
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.models import Policy

_GENERIC_MATCH = "We could not match those details. Check them or contact the agency."
_GENERIC_CLAIM = "We could not find that claim with the details provided."

_OPEN_STATUSES = {
    ClaimStatus.CLAIM_DRAFT.value,
    ClaimStatus.CLAIM_SUBMITTED.value,
    ClaimStatus.VETTING.value,
    ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
}

_PUBLIC_STATUS = {
    ClaimStatus.CLAIM_DRAFT.value: "Received",
    ClaimStatus.CLAIM_SUBMITTED.value: "Received",
    ClaimStatus.VETTING.value: "Under review",
    ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value: "More information needed",
    ClaimStatus.VETTING_PASSED.value: "With the insurer",
    ClaimStatus.SENT_TO_DEFINITE.value: "With the insurer",
    ClaimStatus.DEFINITE_REVIEW.value: "With the insurer",
    ClaimStatus.DEFINITE_APPROVED.value: "Approved — settlement in progress",
    ClaimStatus.PAYMENT_PENDING.value: "Approved — settlement in progress",
    ClaimStatus.PAYMENT_AUTHORIZATION.value: "Approved — settlement in progress",
    ClaimStatus.PAYMENT_AUTHORIZED.value: "Approved — settlement in progress",
    ClaimStatus.PAYMENT_PROCESSING.value: "Payment in progress",
    ClaimStatus.PAYMENT_COMPLETED.value: "Payment completed",
    ClaimStatus.PAYMENT_FAILED.value: "Payment being reviewed",
    ClaimStatus.PAYMENT_REVIEW.value: "Payment being reviewed",
    ClaimStatus.CLIENT_NOTIFIED.value: "Payment completed",
    ClaimStatus.CLOSED.value: "Closed",
    ClaimStatus.VETTING_FAILED.value: "Not approved",
    ClaimStatus.REJECTED.value: "Not approved",
    ClaimStatus.DEFINITE_REJECTED.value: "Not approved",
    ClaimStatus.CANCELLED.value: "Cancelled",
    ClaimStatus.WITHDRAWN.value: "Withdrawn",
}


def policy_lookup_key(value: str) -> str:
    """Certificate, document, and POL numbers compare as letters/digits only."""
    cleaned = "".join(ch for ch in (value or "").strip().upper() if ch.isalnum())
    if len(cleaned) < 4 or len(cleaned) > 64:
        raise ValidationAppError(_GENERIC_MATCH)
    return cleaned


def _sql_lookup_key(column):
    return func.regexp_replace(func.upper(func.coalesce(column, "")), "[^A-Z0-9]", "", "g")


def _safe_norm(fn, value: str | None) -> str | None:
    try:
        return fn(value or "")
    except ValidationAppError:
        return None


def _same(left: str | None, right: str | None) -> bool:
    if left is None or right is None or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _reg_key(value: str | None) -> str | None:
    raw = _safe_norm(normalize_vehicle_registration, value)
    if raw is None:
        compact = (value or "").strip().upper().replace(" ", "").replace("-", "")
        return compact if 3 <= len(compact) <= 15 else None
    return raw.replace(" ", "").replace("-", "")


def phone_candidates(value: str | None) -> frozenset[str]:
    """Compare 07xx / 2547xx / +2547xx as the same Kenyan mobile."""
    raw = _safe_norm(normalize_phone, value)
    if raw is None:
        return frozenset()
    digits = raw.lstrip("+")
    out = {digits}
    if digits.startswith("0") and len(digits) == 10:
        out.add("254" + digits[1:])
    elif digits.startswith("254") and len(digits) == 12:
        out.add("0" + digits[3:])
    elif len(digits) == 9 and digits[0] in {"1", "7"}:
        out.add("254" + digits)
        out.add("0" + digits)
    return frozenset(out)


def phones_match(stored: str | None, provided: str | None) -> bool:
    return bool(phone_candidates(stored) & phone_candidates(provided))


def public_status(status: str) -> str:
    return _PUBLIC_STATUS.get(status, "In progress")


def public_journey(status: str) -> dict[str, Any]:
    """Client-safe progress — never exposes internal workflow codes."""
    key = (status or "").upper()
    declined = key in {
        ClaimStatus.VETTING_FAILED.value,
        ClaimStatus.REJECTED.value,
        ClaimStatus.DEFINITE_REJECTED.value,
    }
    stopped = key in {
        ClaimStatus.CANCELLED.value,
        ClaimStatus.WITHDRAWN.value,
        ClaimStatus.CLOSED.value,
    }
    if declined:
        current_id = "finished"
        waiting_on = None
        now = "This claim was not approved."
        done = ["You filed the claim", "The agency reviewed it"]
        pending: list[str] = []
    elif key == ClaimStatus.CLOSED.value:
        current_id = "finished"
        waiting_on = None
        now = "This claim is closed."
        done = ["You filed the claim", "The agency reviewed it", "The file was settled"]
        pending = []
    elif key in {ClaimStatus.CANCELLED.value, ClaimStatus.WITHDRAWN.value}:
        current_id = "finished"
        waiting_on = None
        now = "This claim is no longer open."
        done = ["You filed the claim"]
        pending = []
    elif key in {
        ClaimStatus.PAYMENT_COMPLETED.value,
        ClaimStatus.CLIENT_NOTIFIED.value,
    }:
        current_id = "finished"
        waiting_on = None
        now = "Settlement is complete."
        done = ["You filed the claim", "The agency reviewed it", "The insurer decided", "Payment was sent"]
        pending = []
    elif key in {
        ClaimStatus.DEFINITE_APPROVED.value,
        ClaimStatus.PAYMENT_PENDING.value,
        ClaimStatus.PAYMENT_AUTHORIZATION.value,
        ClaimStatus.PAYMENT_AUTHORIZED.value,
        ClaimStatus.PAYMENT_PROCESSING.value,
        ClaimStatus.PAYMENT_FAILED.value,
        ClaimStatus.PAYMENT_REVIEW.value,
    }:
        current_id = "settlement"
        waiting_on = "agency"
        now = "The claim was approved. Settlement is underway."
        done = ["You filed the claim", "The agency reviewed it", "The insurer decided"]
        pending = ["Finished"]
    elif key in {
        ClaimStatus.VETTING_PASSED.value,
        ClaimStatus.SENT_TO_DEFINITE.value,
        ClaimStatus.DEFINITE_REVIEW.value,
    }:
        current_id = "insurer"
        waiting_on = "insurer"
        now = "The agency has passed your claim to the insurer. You do not need to do anything unless they ask."
        done = ["You filed the claim", "The agency reviewed it"]
        pending = ["Settlement", "Finished"]
    elif key == ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value:
        current_id = "review"
        waiting_on = "you"
        now = "The agency has paused review until they have a little more from you."
        done = ["You filed the claim"]
        pending = ["Insurer", "Settlement", "Finished"]
    elif key == ClaimStatus.VETTING.value:
        current_id = "review"
        waiting_on = "agency"
        now = "An officer is reviewing your claim against the policy."
        done = ["You filed the claim"]
        pending = ["Insurer", "Settlement", "Finished"]
    else:
        current_id = "review"
        waiting_on = "agency"
        now = "Your report is with the agency. An officer will pick it up shortly."
        done = ["You filed the claim"]
        pending = ["Agency review", "Insurer", "Settlement"]

    order = ["filed", "review", "insurer", "settlement", "finished"]
    labels = {
        "filed": "Filed",
        "review": "Agency review",
        "insurer": "Insurer",
        "settlement": "Settlement",
        "finished": "Finished" if not declined else "Not approved",
    }
    if stopped and key != ClaimStatus.CLOSED.value:
        labels["finished"] = "Closed"
    idx = order.index(current_id)
    steps = []
    for i, step_id in enumerate(order):
        if declined and step_id in {"insurer", "settlement"}:
            state = "skip"
        elif i < idx:
            state = "done"
        elif i == idx:
            state = "current"
        else:
            state = "wait"
        steps.append({"id": step_id, "label": labels[step_id], "state": state})

    waiting_label = {
        "you": "Waiting on you",
        "agency": "Waiting on the agency",
        "insurer": "Waiting on the insurer",
    }.get(waiting_on or "", "")

    return {
        "steps": steps,
        "now": now,
        "waiting_on": waiting_on,
        "waiting_label": waiting_label,
        "done": done,
        "pending": pending,
    }


class GuestClaimService:
    def __init__(self, session: AsyncSession, guest: GuestContext, request: Request) -> None:
        self.session = session
        self.guest = guest
        self.request = request
        self.ctx = guest.as_execution_context()
        self.events = ClaimEventService(session, self.ctx)

    async def file(self, body: GuestClaimCreateRequest) -> dict[str, Any]:
        self.guest.require(GuestCapability.FILE_CLAIM)
        self.guest.require_active_tenant()
        policy_number = policy_lookup_key(body.policy_number)
        registration = normalize_vehicle_registration(body.vehicle_registration)
        id_number = normalize_id_number(body.id_number)
        phone = normalize_phone(body.phone)

        policy, customer = await self._match_active_policy(
            policy_number, registration, id_number, phone
        )
        if policy is None or customer is None:
            raise ValidationAppError(_GENERIC_MATCH)

        await self._adopt_policy_tenant(policy.tenant_id)
        existing = await self.session.scalar(
            select(Claim).where(
                Claim.tenant_id == policy.tenant_id,
                Claim.policy_id == policy.id,
                Claim.status.in_(_OPEN_STATUSES),
            )
        )
        if existing is not None:
            raise ConflictError(
                "A claim is already open for this policy. Use Follow up with the claim number."
            )

        claim = Claim(
            tenant_id=policy.tenant_id,
            branch_id=policy.branch_id,
            customer_id=customer.id,
            policy_id=policy.id,
            created_by_user_id=None,
            assigned_to_user_id=None,
            guest_session_id=self.guest.session_id,
            claim_number=self._claim_number(),
            claim_type=ClaimType.MOTOR.value,
            status=ClaimStatus.CLAIM_SUBMITTED.value,
            channel=ClaimChannel.GUEST.value,
            incident_date=body.incident_date,
            incident_location=body.incident_location.strip(),
            incident_description=body.incident_description.strip(),
            police_abstract_number=(body.police_abstract_number or "").strip() or None,
            vehicle_registration=policy.vehicle_registration,
            vehicle_make=policy.vehicle_make,
            vehicle_model=policy.vehicle_model,
            chassis_number=policy.chassis_number,
            driver_name=(body.driver_name or "").strip() or None,
            claimed_amount=body.claimed_amount,
            currency="KES",
            beneficiary_type="CLIENT",
            beneficiary_reference=customer.phone,
            submitted_at=datetime.now(UTC),
        )
        self.session.add(claim)
        await self.session.flush()
        self.session.add(
            ClaimFollowup(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                followup_type=FollowupType.INTERNAL_REVIEW.value,
                subject="Guest claim awaiting assignment",
                message="A client submitted this claim from the public welcome screen.",
                status=FollowupStatus.PENDING_INTERNAL.value,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="CLAIM_SUBMITTED",
            summary="Client submitted a claim from the welcome screen",
            new_state=claim.status,
            actor_type=ClaimEventActorType.USER.value,
            actor_display_name="Client",
            actor_role="guest",
            actor_user_id=None,
            tenant_id=claim.tenant_id,
        )
        await bind_guest_customer(self.request, customer.id)
        await bind_guest_policy(self.request, policy.id)
        await bind_guest_claim(self.request, claim.id)
        await self._email_filed_claim(claim, policy_number=policy.policy_number)
        return self._public(claim, extra_notice="Keep this claim number for follow-up.")

    async def _email_filed_claim(self, claim: Claim, *, policy_number: str) -> None:
        """Best-effort receipt + PDF. Never fail the guest file on mail errors."""
        from app.core.logging import get_logger
        from app.modules.claims.notify import notify_claim_event
        from app.modules.claims.service import ClaimService
        from app.modules.notifications.enums import NotificationTemplate

        extra = {"policy_number": policy_number or ""}
        try:
            content, filename = await ClaimService(self.session, self.ctx).render_file_pdf(
                claim,
                generated_by="Client",
                generated_by_role="guest",
            )
            from app.modules.files.enums import StoredFileAccessKind, StoredFileSource
            from app.modules.files.registry import persist_mail_pdf

            await persist_mail_pdf(
                self.session,
                self.ctx,
                kind="claim",
                resource_id=claim.id,
                content=content,
                filename=filename,
                access_kind=StoredFileAccessKind.STORED.value,
                customer_id=claim.customer_id,
                source=StoredFileSource.GUEST_SUBMIT.value,
            )
            extra["detail"] = "A PDF copy of this claim is attached."
        except Exception:
            get_logger(__name__).warning(
                "guest_claim_pdf_failed",
                extra={"claim_id": str(claim.id)},
                exc_info=True,
            )
        try:
            await notify_claim_event(
                self.session,
                self.ctx,
                claim=claim,
                template=NotificationTemplate.CLAIM_RECEIVED.value,
                extra=extra,
            )
            if extra.get("detail"):
                from app.modules.files.enums import StoredFileAccessKind, StoredFileSource
                from app.modules.files.registry import persist_mail_pdf

                await persist_mail_pdf(
                    self.session,
                    self.ctx,
                    kind="claim",
                    resource_id=claim.id,
                    content=b"",
                    filename=f"{claim.claim_number or 'claim'}.pdf",
                    access_kind=StoredFileAccessKind.EMAIL.value,
                    customer_id=claim.customer_id,
                    source=StoredFileSource.GUEST_SUBMIT.value,
                    write_bytes=False,
                    metadata={"template": NotificationTemplate.CLAIM_RECEIVED.value},
                )
        except Exception:
            get_logger(__name__).warning(
                "guest_claim_email_failed",
                extra={"claim_id": str(claim.id)},
                exc_info=True,
            )

    async def lookup(self, body: GuestClaimLookupRequest) -> dict[str, Any]:
        self.guest.require(GuestCapability.VIEW_OWN_CLAIM, GuestCapability.FOLLOW_UP_CLAIM)
        self.guest.require_active_tenant()
        claim_number = body.claim_number.strip().upper().replace(" ", "")
        id_number = normalize_id_number(body.id_number)
        phone = normalize_phone(body.phone)
        claim, customer = await self._match_claim(claim_number, id_number, phone)
        if claim is None or customer is None:
            raise ValidationAppError(_GENERIC_CLAIM)
        await self._adopt_policy_tenant(claim.tenant_id)
        claim.guest_session_id = self.guest.session_id
        await bind_guest_claim(self.request, claim.id)
        await bind_guest_customer(self.request, claim.customer_id)
        await bind_guest_policy(self.request, claim.policy_id)
        return await self._bound_public(claim)

    async def get(self, claim_id: UUID) -> dict[str, Any]:
        self.guest.require(GuestCapability.VIEW_OWN_CLAIM)
        claim = await self._owned(claim_id)
        return await self._bound_public(claim)

    async def follow_up(self, claim_id: UUID, message: str) -> dict[str, Any]:
        self.guest.require(GuestCapability.FOLLOW_UP_CLAIM)
        claim = await self._owned(claim_id)
        if claim.status in TERMINAL_STATUSES:
            raise ConflictError("This claim is closed to further client updates")
        note = ClaimNote(
            tenant_id=claim.tenant_id,
            claim_id=claim.id,
            visibility=NoteVisibility.CLIENT.value,
            body=message.strip(),
            created_by_user_id=None,
        )
        self.session.add(note)
        self.session.add(
            ClaimFollowup(
                tenant_id=claim.tenant_id,
                claim_id=claim.id,
                followup_type=FollowupType.CLIENT_INFORMATION.value,
                subject="Client follow-up",
                message=message.strip(),
                status=FollowupStatus.PENDING_INTERNAL.value,
            )
        )
        await self.events.record(
            claim_id=claim.id,
            action="FOLLOWUP_CREATED",
            summary="Client sent a follow-up",
            actor_type=ClaimEventActorType.USER.value,
            actor_display_name="Client",
            actor_role="guest",
            actor_user_id=None,
        )
        return await self._bound_public(claim)

    async def _owned(self, claim_id: UUID) -> Claim:
        assert_guest_owns_claim(self.request, claim_id)
        claim = await self.session.get(Claim, claim_id)
        if claim is None:
            tenant_ids = await guest_fnol_tenant_ids(self.session, self.guest.tenant_id)
            for tid in tenant_ids:
                await set_rls_context(
                    self.session, tenant_id=tid, is_platform_admin=False
                )
                claim = await self.session.get(Claim, claim_id)
                if claim is not None:
                    await self._adopt_policy_tenant(claim.tenant_id)
                    break
            else:
                await set_rls_context(
                    self.session, tenant_id=self.guest.tenant_id, is_platform_admin=False
                )
        if (
            claim is None
            or (
                claim.guest_session_id is not None
                and claim.guest_session_id != self.guest.session_id
            )
        ):
            raise AuthorizationError(_GENERIC_CLAIM)
        return claim

    async def _adopt_policy_tenant(self, tenant_id: UUID) -> None:
        if tenant_id != self.guest.tenant_id:
            await bind_guest_fnol_tenant(self.request, tenant_id)
            self.guest.tenant_id = tenant_id
            self.guest.bind()
            self.ctx = self.guest.as_execution_context()
            self.events = ClaimEventService(self.session, self.ctx)
        await set_rls_context(
            self.session, tenant_id=tenant_id, is_platform_admin=False
        )

    async def _policies_for_number(
        self, tenant_id: UUID, policy_number: str
    ) -> list[Policy]:
        await set_rls_context(
            self.session, tenant_id=tenant_id, is_platform_admin=False
        )
        cert_ids = select(Certificate.policy_id).where(
            Certificate.tenant_id == tenant_id,
            or_(
                _sql_lookup_key(Certificate.certificate_number) == policy_number,
                _sql_lookup_key(Certificate.external_certificate_ref) == policy_number,
            ),
        )
        return list(
            (
                await self.session.scalars(
                    select(Policy).where(
                        Policy.tenant_id == tenant_id,
                        or_(
                            _sql_lookup_key(Policy.policy_number) == policy_number,
                            _sql_lookup_key(Policy.provider_document_number)
                            == policy_number,
                            _sql_lookup_key(Policy.certificate_ref) == policy_number,
                            Policy.id.in_(cert_ids),
                        ),
                    )
                )
            ).all()
        )

    def _identity_matches(
        self,
        policy: Policy,
        customer: Customer | None,
        registration: str,
        id_number: str,
        phone: str,
    ) -> bool:
        return (
            customer is not None
            and customer.tenant_id == policy.tenant_id
            and customer.deleted_at is None
            and policy.status == PolicyStatus.ACTIVE.value
            and _same(_reg_key(policy.vehicle_registration), _reg_key(registration))
            and _same(_safe_norm(normalize_id_number, customer.id_number), id_number)
            and phones_match(customer.phone, phone)
        )

    async def _match_active_policy(
        self,
        policy_number: str,
        registration: str,
        id_number: str,
        phone: str,
    ) -> tuple[Policy | None, Customer | None]:
        home = self.guest.tenant_id
        matches: list[tuple[Policy, Customer]] = []
        try:
            for tid in await guest_fnol_tenant_ids(self.session, home):
                policies = await self._policies_for_number(tid, policy_number)
                if not policies:
                    continue
                customers = {
                    row.id: row
                    for row in (
                        await self.session.scalars(
                            select(Customer).where(
                                Customer.id.in_({policy.customer_id for policy in policies})
                            )
                        )
                    ).all()
                }
                for policy in policies:
                    customer = customers.get(policy.customer_id)
                    if self._identity_matches(
                        policy, customer, registration, id_number, phone
                    ):
                        assert customer is not None
                        matches.append((policy, customer))
        finally:
            await set_rls_context(
                self.session, tenant_id=home, is_platform_admin=False
            )
        if len(matches) != 1:
            return None, None
        return matches[0]

    async def _match_claim(
        self, claim_number: str, id_number: str, phone: str
    ) -> tuple[Claim | None, Customer | None]:
        home = self.guest.tenant_id
        claim_key = func.replace(func.upper(func.coalesce(Claim.claim_number, "")), " ", "")
        matches: list[tuple[Claim, Customer]] = []
        try:
            for tid in await guest_fnol_tenant_ids(self.session, home):
                await set_rls_context(
                    self.session, tenant_id=tid, is_platform_admin=False
                )
                claim = await self.session.scalar(
                    select(Claim).where(
                        Claim.tenant_id == tid,
                        claim_key == claim_number,
                    )
                )
                if claim is None:
                    continue
                customer = await self.session.get(Customer, claim.customer_id)
                if (
                    customer is not None
                    and customer.tenant_id == claim.tenant_id
                    and _same(_safe_norm(normalize_id_number, customer.id_number), id_number)
                    and phones_match(customer.phone, phone)
                ):
                    matches.append((claim, customer))
        finally:
            await set_rls_context(
                self.session, tenant_id=home, is_platform_admin=False
            )
        if len(matches) != 1:
            return None, None
        return matches[0]

    async def _bound_public(self, claim: Claim) -> dict[str, Any]:
        notes = list(
            (
                await self.session.scalars(
                    select(ClaimNote)
                    .where(
                        ClaimNote.claim_id == claim.id,
                        ClaimNote.visibility == NoteVisibility.CLIENT.value,
                    )
                    .order_by(ClaimNote.created_at.asc())
                )
            ).all()
        )
        return self._public(
            claim,
            extras={
                "needs_information": claim.status
                == ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
                "journey": public_journey(claim.status),
                "messages": [
                    {
                        "from": "you" if row.created_by_user_id is None else "agency",
                        "body": row.body,
                        "created_at": row.created_at,
                    }
                    for row in notes
                ],
            },
        )

    def _public(
        self,
        claim: Claim,
        *,
        extras: dict[str, Any] | None = None,
        extra_notice: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "id": str(claim.id),
            "claim_number": claim.claim_number,
            "public_status": public_status(claim.status),
            "vehicle_registration": claim.vehicle_registration,
            "incident_date": claim.incident_date,
            "submitted_at": claim.submitted_at,
            "notice": extra_notice,
        }
        if extras:
            payload.update(extras)
        return payload

    @staticmethod
    def _claim_number() -> str:
        import secrets

        return f"CLM-{datetime.now(UTC).year}-{secrets.token_hex(4).upper()}"
