"""Certificate generation after verified payment / policy activation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database.enums import JobStatus, JobType
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger
from app.core.security.context import SecurityContext
from app.integrations.insurance.ports import InsuranceProvider
from app.core.logging.context import get_correlation_id, get_job_id, get_request_id
from app.modules.audit.service import AuditService
from app.modules.certificates.access_enums import CertificateAccessKind, CertificateAccessSource
from app.modules.certificates.access_models import CertificateFileAccess
from app.modules.certificates.models import Certificate
from app.modules.certificates.repository import CertificateRepository
from app.modules.certificates.storage import (
    local_copy_exists,
    read_local_certificate,
    store_certificate_pdf,
)
from app.modules.customers.repository import CustomerRepository
from app.modules.jobs.service import JobService
from app.modules.notifications.pdf_mail import enqueue_downloaded_pdf_emails
from app.modules.payments.enums import CertificateStatus
from app.modules.policies.enums import PolicyStatus
from app.modules.policies.repository import PolicyRepository

logger = get_logger(__name__)

_CERT_NUMBER_KEYS = (
    "certNo",
    "CertNo",
    "certificateId",
    "CertificateNo",
    "certificateNumber",
    "CertificateNumber",
    "certNumber",
)

# Definite UAT often returns HTTP 200 with this copy before the note is ready.
_TRANSIENT_CERT_TOKENS = (
    "try again later",
    "please try again",
    "temporarily",
    "please wait",
    "not ready",
    "processing",
    "timed out",
    "timeout",
    "busy",
    "fetch failed",
    "undici",
    "typeerror",
)
# Validation from Definite — retrying generateCertificate will not fix these.
_NON_TRANSIENT_CERT_TOKENS = (
    "policy holder is required",
    "policyholder is required",
    "client is required",
)


def _remote_file_ref(row: Certificate) -> str | None:
    """Internal locator only — never returned to clients."""
    for value in (row.provider_cert_url, row.storage_key):
        text = str(value or "").strip()
        if text.startswith(("http://", "https://")) and "example.local" not in text:
            return text
    return None


def file_available(row: Certificate) -> bool:
    """True when the download endpoint can attempt to stream a PDF."""
    return local_copy_exists(row.local_file_path) or _remote_file_ref(row) is not None


def to_public(
    row: Certificate,
    *,
    customer_name: str | None = None,
    vehicle_registration: str | None = None,
) -> dict[str, Any]:
    """Client projection. File locations stay on the server; bytes go through download."""
    return {
        "id": str(row.id),
        "policy_id": str(row.policy_id),
        "payment_id": str(row.payment_id) if row.payment_id else None,
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "customer_name": customer_name,
        "vehicle_registration": vehicle_registration,
        "certificate_number": row.certificate_number,
        "status": row.status,
        "external_certificate_ref": row.external_certificate_ref,
        "file_available": file_available(row),
        "local_copy_available": local_copy_exists(row.local_file_path),
        "local_stored_at": row.local_stored_at.isoformat() if row.local_stored_at else None,
        "content_sha256": row.content_sha256,
        "file_size_bytes": row.file_size_bytes,
        "access_count": int(row.access_count or 0),
        "last_accessed_at": (
            row.last_accessed_at.isoformat() if row.last_accessed_at else None
        ),
        "last_accessed_by_user_id": (
            str(row.last_accessed_by_user_id) if row.last_accessed_by_user_id else None
        ),
        "download_url_expires_at": (
            row.download_url_expires_at.isoformat() if row.download_url_expires_at else None
        ),
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "failure_message": row.failure_message,
        "job_id": row.job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def access_to_public(row: CertificateFileAccess) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "certificate_id": str(row.certificate_id),
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "access_kind": row.access_kind,
        "source": row.source,
        "result": row.result,
        "content_sha256": row.content_sha256,
        "file_size_bytes": row.file_size_bytes,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "request_id": row.request_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _extract_cert_url(payload: dict[str, Any] | None) -> str | None:
    """Pull certURL from Definite payloads (top-level or nested under data)."""
    if not isinstance(payload, dict):
        return None
    for key in ("certURL", "certUrl", "certificateUrl", "CertificateUrl", "pdfUrl"):
        value = payload.get(key)
        if value and "example.local" not in str(value):
            return str(value)
    nested = payload.get("data")
    if isinstance(nested, dict):
        return _extract_cert_url(nested)
    return None


def _flatten_cert_payload(remote: Any) -> dict[str, Any]:
    remote_dict = remote if isinstance(remote, dict) else {"data": remote}
    nested = remote_dict.get("data")
    if isinstance(nested, dict) and not _extract_cert_url(remote_dict):
        remote_dict = {**remote_dict, **nested}
    elif isinstance(nested, str) and nested.strip() and not remote_dict.get("message"):
        remote_dict = {**remote_dict, "message": nested.strip()}
    return remote_dict


def _cert_number(remote_dict: dict[str, Any]) -> str | None:
    for key in _CERT_NUMBER_KEYS:
        value = remote_dict.get(key)
        if value and str(value).strip() and "example.local" not in str(value):
            return str(value).strip()
    nested = remote_dict.get("data")
    if isinstance(nested, dict):
        return _cert_number(nested)
    return None


def _definite_cert_issued(remote_dict: dict[str, Any]) -> bool:
    """True when Definite returned a real certificate (URL and/or cert number)."""
    has_artifact = bool(_extract_cert_url(remote_dict) or _cert_number(remote_dict))
    if remote_dict.get("success") is False and not has_artifact:
        return False
    return has_artifact


def _raw_definite_message(remote_dict: dict[str, Any]) -> str:
    # Prefer the primary business ``message`` — LIVE often puts opaque codes like
    # ``ER001: You tried invalid api`` in errorMessage while message still says
    # "try again later" (retryable settle race).
    for key in ("message", "Message", "errorMessage", "error"):
        value = remote_dict.get(key)
        if value and str(value).strip():
            return str(value).strip()
    nested = remote_dict.get("data")
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return "Certificate generation failed at Definite"


def _definite_error_message(remote_dict: dict[str, Any], *, for_refresh: bool = False) -> str:
    from app.integrations.insurance.definite_assurance.client import public_definite_message

    candidates = [
        str(remote_dict.get(key) or "").strip()
        for key in ("message", "Message", "errorMessage", "error")
    ]
    candidates = [c for c in candidates if c]
    raw = candidates[0] if candidates else "Certificate generation failed at Definite"
    joined = " | ".join(candidates).lower()
    # Definite puts a "new quote" double-insurance tip in errorMessage when
    # generateCertificate is retried for an already-issued note. That advice is
    # wrong when the user is only trying to view/download an existing PDF.
    if for_refresh and any(
        token in joined
        for token in (
            "already covered",
            "already exists",
            "obtain a new quote",
            "cover start date",
            "same registration",
        )
    ):
        return (
            "The insurer could not refresh this certificate PDF. "
            "The cover is already active — try again shortly, or contact support "
            "with the certificate number if the file stays unavailable."
        )
    # Prefer a clearer companion field when message is the generic try-later shell.
    lower = raw.lower()
    if "try again later" in lower or lower.startswith("er001"):
        for alt in candidates[1:]:
            alt_l = alt.lower()
            if "insufficient" in alt_l or "wallet" in alt_l or "balance" in alt_l:
                return public_definite_message(alt)
            if alt_l.startswith("er004") or "commencing date" in alt_l:
                return public_definite_message(alt)
            if "already covered" in alt_l or "obtain a new quote" in alt_l:
                return public_definite_message(alt)
    return public_definite_message(
        raw,
        fallback="Certificate generation failed. Please try issuing it again.",
    )


def _transient_cert_failure(remote_dict: dict[str, Any]) -> bool:
    """True when Definite 200'd without a cert and the note may still be settling."""
    from app.integrations.insurance.definite_assurance.client import provider_message_is_internal

    if _definite_cert_issued(remote_dict):
        return False
    texts = [
        str(remote_dict.get(key) or "").strip().lower()
        for key in ("message", "Message", "errorMessage", "error", "errorCode")
    ]
    texts = [t for t in texts if t]
    joined = " | ".join(texts)
    if any(provider_message_is_internal(t) for t in texts):
        return True
    if any(token in joined for token in _NON_TRANSIENT_CERT_TOKENS):
        return False
    # LIVE sometimes pairs ER001 with "try again later" while the note settles.
    if "try again later" in joined or "please try again" in joined:
        return True
    if any(token in joined for token in _TRANSIENT_CERT_TOKENS):
        return True
    if joined in {
        "certificate generation failed at definite",
        "certificate generation failed",
        "",
    }:
        return True
    if "er001" in joined:
        return True
    return False


class CertificateService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: SecurityContext,
        provider: InsuranceProvider,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.provider = provider
        self.repo = CertificateRepository(session, ctx)
        self.policies = PolicyRepository(session, ctx)
        self.audit = AuditService(session)
        self.jobs = JobService(session, ctx)

    async def _resolve_policy_holder_oid(self, policy: Any) -> int | None:
        from app.modules.insurance.provider_fields import extract_definite_client_oid

        summary = policy.provider_payload_summary if isinstance(
            getattr(policy, "provider_payload_summary", None), dict
        ) else {}
        oid = extract_definite_client_oid(summary)
        if oid is not None:
            return oid
        customer_id = getattr(policy, "customer_id", None)
        if customer_id is None:
            return None
        try:
            customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                customer_id
            )
        except Exception:
            return None
        return extract_definite_client_oid(customer)

    async def _resolve_policy_holder_email(self, policy: Any) -> str | None:
        """Customer email stored locally — Definite LIVE needs it on cert issue."""
        from app.modules.insurance.provider_fields import extract_holder_email

        customer = None
        customer_id = getattr(policy, "customer_id", None)
        if customer_id is not None:
            try:
                customer = await CustomerRepository(self.session, self.ctx).get_active_by_id(
                    customer_id
                )
            except Exception as exc:
                logger.warning(
                    "certificate_holder_lookup_failed",
                    policy_id=str(getattr(policy, "id", "")),
                    error_type=type(exc).__name__,
                )
        email = extract_holder_email(customer, getattr(policy, "provider_payload_summary", None))
        if email is None:
            logger.warning(
                "certificate_holder_email_missing",
                policy_id=str(getattr(policy, "id", "")),
            )
        return email

    async def list(
        self,
        *,
        page: int,
        limit: int,
        policy_id: UUID | None,
        status: str | None,
    ) -> tuple[list[Certificate], int]:
        self.ctx.require_staff_principal()
        return await self.repo.search(
            policy_id=policy_id,
            status=status,
            offset=(page - 1) * limit,
            limit=limit,
        )

    async def customer_names_for(self, rows: list[Certificate]) -> dict[UUID, str]:
        customer_ids = list({row.customer_id for row in rows if row.customer_id})
        if not customer_ids:
            return {}
        return await CustomerRepository(self.session, self.ctx).display_names_by_ids(
            customer_ids
        )

    async def vehicle_registrations_for(self, rows: list[Certificate]) -> dict[UUID, str]:
        policy_ids = list({row.policy_id for row in rows if row.policy_id})
        if not policy_ids:
            return {}
        return await self.policies.vehicle_registrations_by_ids(policy_ids)

    async def get(self, certificate_id: UUID) -> Certificate:
        return await self.repo.get(certificate_id)

    async def generate_for_policy(
        self,
        policy_id: UUID,
        *,
        payment_id: UUID | None = None,
        approve_provider_note: bool = True,
        definite_payment_method: int | None = None,
    ) -> Certificate:
        """Issue certificate after local payment success.

        Always runs Definite ``initiatePayment`` at most once via
        ``DefiniteSettlementService`` (idempotent on ``provider_payment_approved``).

        - DEFINITE_WALLET / DEFINITE_MPESA: usually already approved at pay → skip
        - BIRDVIEW: approve with wallet (3) after BirdView SUCCESS, then generateCertificate

        ``approve_provider_note=False`` forces skip (legacy / already settled elsewhere).
        ``definite_payment_method`` overrides the rail default when settling now.
        """
        self.ctx.require_active_tenant()
        from app.modules.system_config.service import SystemConfigService

        await SystemConfigService(self.session).require_service("certificates")
        policy = await self.policies.get(policy_id)
        self.ctx.assert_branch_access(getattr(policy, "branch_id", None))
        if policy.status not in {
            PolicyStatus.ACTIVE.value,
            PolicyStatus.PENDING_CERTIFICATE.value,
        }:
            raise ValidationAppError("Policy must be active or pending certificate")

        from app.modules.payments.enums import PaymentStatus
        from app.modules.payments.repository import PaymentRepository

        pay_repo = PaymentRepository(self.session, self.ctx)
        if payment_id is not None:
            payment = await pay_repo.get(payment_id)
            if payment.policy_id != policy.id:
                raise ValidationAppError("Payment does not belong to this policy")
            if payment.status != PaymentStatus.SUCCESS.value:
                raise ValidationAppError("Certificate requires a successful payment")
        else:
            payment = await pay_repo.find_latest_for_policy(
                policy.id, status=PaymentStatus.SUCCESS.value
            )
            if payment is None:
                raise ValidationAppError("Certificate requires a successful payment")
            payment_id = payment.id

        existing = await self.repo.find_by_policy(policy_id)
        if existing and existing.status == CertificateStatus.GENERATED.value:
            storage = str(existing.storage_key or "")
            provider_url = str(getattr(existing, "provider_cert_url", None) or "")
            has_usable_url = (
                (bool(storage) and "example.local" not in storage)
                or (bool(provider_url) and "example.local" not in provider_url)
            )
            # Already issued — return immediately so pay-step UI can advance
            # even if local PDF caching is still warming up.
            if has_usable_url:
                return existing

        job = await self.jobs.create(
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            job_type=JobType.CERTIFICATE_GENERATION,
        )
        cert_number = (
            existing.certificate_number
            if existing and existing.certificate_number
            else f"CERT-{uuid4().hex[:10].upper()}"
        )
        if existing:
            cert = existing
            cert.status = CertificateStatus.PENDING.value
            cert.failure_message = None
            cert.job_id = job.job_key
            cert.payment_id = payment_id or cert.payment_id
        else:
            cert = Certificate(
                tenant_id=self.ctx.tenant_id,
                policy_id=policy.id,
                payment_id=payment_id,
                customer_id=policy.customer_id,
                branch_id=getattr(policy, "branch_id", None),
                generated_by_user_id=self.ctx.actor_user_id,
                certificate_number=cert_number,
                status=CertificateStatus.PENDING.value,
                job_id=job.job_key,
            )
            await self.repo.add(cert)
        await self.session.flush()

        await self.jobs.add_event(job, "EXTERNAL_REQUEST_STARTED", message="generate_certificate")
        summary = policy.provider_payload_summary or {}
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
        if not proposal_ref or not note_oid:
            raise ValidationAppError(
                "Policy is missing Definite proposal/note details required for certificate",
                details=[{"proposal": proposal_ref, "note_oid": note_oid}],
            )

        holder_oid = await self._resolve_policy_holder_oid(policy)
        holder_email = await self._resolve_policy_holder_email(policy)
        if holder_oid is not None:
            summary = dict(policy.provider_payload_summary or {})
            if summary.get("definite_client_oid") != holder_oid:
                summary["definite_client_oid"] = holder_oid
                policy.provider_payload_summary = summary
                await self.session.flush()
        if holder_email and isinstance(policy.provider_payload_summary, dict):
            summary = dict(policy.provider_payload_summary or {})
            if summary.get("customer_email") != holder_email:
                summary["customer_email"] = holder_email
                policy.provider_payload_summary = summary
                await self.session.flush()

        from app.modules.insurance.definite_settlement import DefiniteSettlementService
        from app.modules.payments.repository import PaymentRepository
        from app.modules.payments.settlement import DefinitePaymentMethod, resolve_settlement_plan

        settle_method = definite_payment_method
        receipt: str | None = None
        phone: str | None = None
        if payment_id is not None:
            try:
                payment = await PaymentRepository(self.session, self.ctx).get(payment_id)
                receipt = payment.provider_receipt or payment.reference
                phone = payment.phone
                if settle_method is None:
                    try:
                        plan = resolve_settlement_plan(payment.method)
                        settle_method = int(plan.definite_payment_method)
                    except ValidationAppError:
                        settle_method = int(DefinitePaymentMethod.WALLET)
            except Exception:
                pass
        if settle_method is None:
            settle_method = int(
                (policy.provider_payload_summary or {}).get("definite_payment_method")
                or DefinitePaymentMethod.WALLET
            )

        try:
            settled_now = False
            if approve_provider_note:
                settled = await DefiniteSettlementService(
                    self.session, self.ctx, self.provider
                ).approve_note_once(
                    policy,
                    definite_payment_method=settle_method,
                    phone=phone,
                    receipt=(receipt or policy.provider_payment_txn or f"SSN{note_oid}")[:20],
                    job=job,
                )
                settled_now = not bool(settled.get("skipped"))
            else:
                summary = dict(policy.provider_payload_summary or {})
                summary["provider_payment_approved"] = True
                summary["provider_payment_skipped_reason"] = "approve_provider_note_false"
                policy.provider_payload_summary = summary
                await self.session.flush()
                await self.jobs.add_event(
                    job,
                    "EXTERNAL_REQUEST_SKIPPED",
                    message="initiatePayment skipped by caller",
                )

            # LIVE needs a short beat after wallet settle; UAT races harder.
            # Optimistic first attempt still runs inside the retry helper.
            if settled_now:
                await asyncio.sleep(1.25)

            remote_dict = await self._generate_certificate_with_retry(
                proposal_ref=proposal_ref,
                note_oid=note_oid,
                policy=policy,
                cert_number=cert_number,
                holder_oid=holder_oid,
                holder_email=holder_email,
                settle_just_completed=settled_now,
            )
            cert_url = _extract_cert_url(remote_dict)
            if not _definite_cert_issued(remote_dict):
                raise ValidationAppError(
                    _definite_error_message(remote_dict),
                )
        except ValidationAppError as exc:
            cert.status = CertificateStatus.FAILED.value
            cert.failure_message = str(exc.message or "Provider certificate generation failed")[:500]
            await self.session.flush()
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="CERTIFICATE_PROVIDER_FAILED",
            )
            raise
        except Exception:
            cert.status = CertificateStatus.FAILED.value
            cert.failure_message = "Provider certificate generation failed"
            await self.session.flush()
            await self.jobs.transition(
                job,
                JobStatus.WAITING_EXTERNAL_SERVICE,
                error_code="CERTIFICATE_PROVIDER_FAILED",
            )
            raise

        await self.jobs.add_event(job, "EXTERNAL_RESPONSE_RECEIVED", message="generate_certificate")
        # Do not block issuance on Azure blob readiness — download polls the URL.
        # One quick probe only (no sleep loop) so clients get the cert id faster.
        if cert_url:
            await _wait_for_remote_pdf(str(cert_url), attempts=1)
        cert.status = CertificateStatus.GENERATED.value
        cert.external_certificate_ref = str(
            _cert_number(remote_dict)
            or remote_dict.get("id")
            or cert_number
        )
        cert.provider_payload = remote_dict
        cert.job_id = job.job_key
        cert.correlation_id = job.job_key
        if cert_url:
            cert.storage_key = str(cert_url)
            cert.provider_cert_url = str(cert_url)
            persisted = await self._try_persist_local_pdf(cert, policy, str(cert_url))
            if not persisted:
                # One more fetch+store attempt before we hand the cert to the client.
                await self._try_persist_local_pdf(cert, policy, str(cert_url))
            # Always mirror into email-pdfs so view/download can recover if the
            # primary certificates/ object is missing after a deploy.
            if cert.local_file_path:
                local_bytes = read_local_certificate(cert.local_file_path)
                if local_bytes:
                    try:
                        from app.core.security.filenames import sanitize_download_filename
                        from app.modules.files.enums import StoredFileAccessKind
                        from app.modules.files.registry import persist_mail_pdf

                        await persist_mail_pdf(
                            self.session,
                            self.ctx,
                            kind="certificate",
                            resource_id=cert.id,
                            content=local_bytes,
                            filename=sanitize_download_filename(
                                f"{cert.external_certificate_ref or cert.certificate_number}.pdf"
                            ),
                            access_kind=StoredFileAccessKind.STORED.value,
                            customer_id=cert.customer_id or getattr(policy, "customer_id", None),
                        )
                    except Exception:
                        logger.warning(
                            "certificate_mail_pdf_persist_failed",
                            certificate_id=str(cert.id),
                            exc_info=True,
                        )
        cert.generated_at = datetime.now(UTC)
        policy.certificate_ref = cert.external_certificate_ref
        # Mirror certificate outcome onto policy summary for customer reopen
        summary = dict(policy.provider_payload_summary or {})
        summary["certificate"] = {
            "certificate_id": str(cert.id),
            "certificate_number": cert.certificate_number,
            "external_certificate_ref": cert.external_certificate_ref,
            "file_available": file_available(cert),
            "generated_at": cert.generated_at.isoformat() if cert.generated_at else None,
        }
        policy.provider_payload_summary = summary
        if policy.status == PolicyStatus.PENDING_CERTIFICATE.value:
            policy.status = PolicyStatus.ACTIVE.value
        policy.version += 1
        await self.session.flush()
        await self.jobs.transition(job, JobStatus.COMPLETED)
        await self.audit.record(
            action="certificate.generate",
            resource="certificate",
            resource_id=str(cert.id),
            tenant_id=self.ctx.tenant_id,
            user_id=self.ctx.actor_user_id,
            metadata={
                "policy_id": str(policy.id),
                "certificate_number": cert.certificate_number,
                "local_copy": bool(cert.local_file_path),
                "local_file_path": cert.local_file_path,
            },
        )
        return cert

    async def _record_file_access(
        self,
        cert: Certificate,
        *,
        access_kind: CertificateAccessKind | str,
        source: CertificateAccessSource | str,
        result: str = "SUCCESS",
        ip_address: str | None = None,
        user_agent: str | None = None,
        failure_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        count_as_user_access: bool = False,
    ) -> CertificateFileAccess:
        event = CertificateFileAccess(
            tenant_id=cert.tenant_id,
            certificate_id=cert.id,
            policy_id=cert.policy_id,
            customer_id=cert.customer_id,
            user_id=self.ctx.actor_user_id,
            access_kind=str(access_kind),
            source=str(source),
            result=result,
            local_file_path=cert.local_file_path,
            provider_cert_url=cert.provider_cert_url or cert.storage_key,
            content_sha256=cert.content_sha256,
            file_size_bytes=cert.file_size_bytes,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
            job_id=get_job_id() or cert.job_id,
            failure_message=failure_message,
            metadata_json=metadata or {},
        )
        self.session.add(event)
        if count_as_user_access and result == "SUCCESS":
            cert.last_accessed_at = datetime.now(UTC)
            cert.last_accessed_by_user_id = self.ctx.actor_user_id
            cert.access_count = int(cert.access_count or 0) + 1
        await self.session.flush()
        return event

    async def list_file_accesses(
        self,
        certificate_id: UUID,
        *,
        page: int = 1,
        limit: int = 50,
    ) -> tuple["list[CertificateFileAccess]", int]:
        from sqlalchemy import func, select

        self.ctx.require_staff_principal()
        cert = await self.repo.get(certificate_id)
        base = select(CertificateFileAccess).where(
            CertificateFileAccess.tenant_id == self.ctx.tenant_id,
            CertificateFileAccess.certificate_id == cert.id,
        )
        count_stmt = (
            select(func.count())
            .select_from(CertificateFileAccess)
            .where(
                CertificateFileAccess.tenant_id == self.ctx.tenant_id,
                CertificateFileAccess.certificate_id == cert.id,
            )
        )
        total = int(await self.session.scalar(count_stmt) or 0)
        stmt = (
            base.order_by(CertificateFileAccess.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return rows, total

    async def _try_persist_local_pdf(
        self,
        cert: Certificate,
        policy: Any,
        url: str,
    ) -> bool:
        """Download provider PDF into the secure local store when available."""
        content = await _fetch_remote_pdf(url)
        if content is None:
            return False
        try:
            stored = store_certificate_pdf(
                tenant_id=cert.tenant_id,
                policy_id=policy.id,
                certificate_id=cert.id,
                content=content,
            )
        except ValueError:
            return False
        cert.local_file_path = stored.relative_path
        cert.local_stored_at = datetime.now(UTC)
        cert.content_sha256 = stored.sha256
        cert.file_size_bytes = stored.size_bytes
        await self._record_file_access(
            cert,
            access_kind=CertificateAccessKind.STORED,
            source=CertificateAccessSource.SYSTEM,
            metadata={"bytes": stored.size_bytes, "sha256": stored.sha256},
        )
        return True

    async def _generate_certificate_with_retry(
        self,
        *,
        proposal_ref: Any,
        note_oid: Any,
        policy: Any,
        cert_number: str,
        holder_oid: int | None = None,
        holder_email: str | None = None,
        settle_just_completed: bool = False,
    ) -> dict[str, Any]:
        """generateCertificate only — never re-runs initiatePayment.

        Definite UAT commonly returns HTTP 200 with
        ``Certificate generation failed. Please try again later.`` a few seconds
        after wallet settle. Retry that body, not only transport errors.
        """
        from app.modules.insurance.provider_fields import (
            definite_holder_fields,
            extract_holder_email,
        )

        email = extract_holder_email(
            {"email": holder_email}, getattr(policy, "provider_payload_summary", None)
        )
        payload = {
            "proposal": proposal_ref,
            "NoteOID": note_oid,
            "policyNumber": policy.policy_number,
            "policyId": policy.external_policy_ref or "",
            "registration": policy.vehicle_registration,
            "certificateNumber": cert_number,
            **definite_holder_fields(holder_oid, getattr(policy, "provider_payload_summary", None)),
            **({"email": email} if email else {}),
        }
        last_error: Exception | None = None
        last_payload: dict[str, Any] = {}
        # 3 attempts with flatter backoff (≤ ~6s sleep) vs previous 4× / 2.5n.
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                remote = await self.provider.generate_certificate(payload)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "definite_generate_certificate_error",
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                if attempt < attempts:
                    await asyncio.sleep(min(1.25 * attempt, 3.5))
                    continue
                raise

            remote_dict = _flatten_cert_payload(remote)
            last_payload = remote_dict
            issued = _definite_cert_issued(remote_dict)
            logger.info(
                "definite_generate_certificate_result",
                attempt=attempt,
                issued=issued,
                success=remote_dict.get("success"),
                message=_definite_error_message(remote_dict)[:180] if not issued else None,
                has_cert_url=bool(_extract_cert_url(remote_dict)),
            )
            if issued:
                return remote_dict
            if attempt < attempts and _transient_cert_failure(remote_dict):
                # After a just-completed settle, give Definite a short beat before retry.
                delay = 2.0 if settle_just_completed and attempt == 1 else min(1.5 * attempt, 3.5)
                await asyncio.sleep(delay)
                continue
            break
        if last_error is not None and not last_payload:
            raise last_error
        return last_payload

    async def download_pdf(
        self,
        certificate_id: UUID,
        *,
        access_kind: CertificateAccessKind | str = CertificateAccessKind.VIEW,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[bytes, str]:
        """Stream the certificate PDF. Prefer local copy; else fetch remote and store.

        Important: any URL / cooldown we persist must be ``commit``-ed before raising
        the retryable error. ``get_db`` rolls back on exceptions, which previously
        wiped ``storage_key`` and caused endless ``generateCertificate`` spam.
        """
        self.ctx.require_active_tenant()
        from app.core.security.filenames import sanitize_download_filename

        cert = await self.repo.get(certificate_id)
        self.ctx.assert_branch_access(getattr(cert, "branch_id", None))
        filename = sanitize_download_filename(
            f"{cert.external_certificate_ref or cert.certificate_number}.pdf"
        )
        kind = CertificateAccessKind(str(access_kind))

        async def _succeed(
            content: bytes,
            *,
            source: CertificateAccessSource,
        ) -> tuple[bytes, str]:
            await self._record_file_access(
                cert,
                access_kind=kind,
                source=source,
                ip_address=ip_address,
                user_agent=user_agent,
                count_as_user_access=True,
                metadata={"filename": filename, "bytes": len(content)},
            )
            await self.audit.record(
                action=f"certificate.{kind.value.lower()}",
                resource="certificate",
                resource_id=str(cert.id),
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.actor_user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "local_file_path": cert.local_file_path,
                    "source": str(source),
                    "access_kind": str(kind),
                },
            )
            if kind == CertificateAccessKind.DOWNLOAD:
                from app.modules.policies.models import Policy

                policy = await self.session.get(Policy, cert.policy_id)
                customer_id = cert.customer_id or getattr(policy, "customer_id", None)
                try:
                    from app.modules.files.enums import StoredFileAccessKind
                    from app.modules.files.registry import persist_mail_pdf

                    await persist_mail_pdf(
                        self.session,
                        self.ctx,
                        kind="certificate",
                        resource_id=cert.id,
                        content=content,
                        filename=filename,
                        access_kind=StoredFileAccessKind.DOWNLOAD.value,
                        customer_id=customer_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                except Exception:
                    from app.core.logging import get_logger

                    get_logger(__name__).warning(
                        "certificate_pdf_registry_failed",
                        extra={"certificate_id": str(cert.id)},
                        exc_info=True,
                    )
                await enqueue_downloaded_pdf_emails(
                    self.session,
                    self.ctx,
                    kind="certificate",
                    resource_id=cert.id,
                    customer_id=customer_id,
                    content=content,
                    filename=filename,
                    context={
                        "certificate_number": cert.certificate_number,
                        "policy_number": getattr(policy, "policy_number", "") or "",
                        "vehicle_registration": (
                            getattr(policy, "vehicle_registration", "") or ""
                        ),
                        "external_certificate_ref": cert.external_certificate_ref or "",
                    },
                    already_stored=True,
                )
            else:
                try:
                    from app.modules.files.enums import StoredFileAccessKind
                    from app.modules.files.registry import persist_mail_pdf

                    await persist_mail_pdf(
                        self.session,
                        self.ctx,
                        kind="certificate",
                        resource_id=cert.id,
                        content=content,
                        filename=filename,
                        access_kind=StoredFileAccessKind.VIEW.value,
                        customer_id=cert.customer_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                except Exception:
                    from app.core.logging import get_logger

                    get_logger(__name__).warning(
                        "certificate_pdf_registry_failed",
                        extra={"certificate_id": str(cert.id)},
                        exc_info=True,
                    )
            return content, filename

        async def _fail(message: str, *, retryable: bool) -> None:
            await self._record_file_access(
                cert,
                access_kind=CertificateAccessKind.FETCH_FAILED,
                source=CertificateAccessSource.REMOTE_PROVIDER,
                result="FAILED",
                ip_address=ip_address,
                user_agent=user_agent,
                failure_message=message[:500],
                metadata={"retryable": retryable, "requested_kind": str(kind)},
            )
            # Commit before raise — get_db rolls back on exceptions
            await self.session.commit()
            raise ValidationAppError(
                message,
                details=[{"retryable": retryable}],
            )

        # Prefer durable object-store / local copy — never re-hit Azure if we already have the PDF
        if cert.local_file_path:
            local = read_local_certificate(cert.local_file_path)
            if local is not None:
                return await _succeed(local, source=CertificateAccessSource.LOCAL)

        # Recover when DB path is missing/stale but the canonical GCS object exists
        # (e.g. objects synced from staging → production prefix).
        try:
            from app.modules.certificates.storage import build_relative_path

            canonical = build_relative_path(
                tenant_id=cert.tenant_id,
                policy_id=cert.policy_id,
                certificate_id=cert.id,
            )
            recovered = read_local_certificate(canonical)
            if recovered is not None:
                cert.local_file_path = canonical
                await self.session.commit()
                return await _succeed(recovered, source=CertificateAccessSource.LOCAL)
        except Exception:
            pass

        # Mail-PDF registry copy (written on successful view/download) — same bytes,
        # different key layout under email-pdfs/.
        try:
            from app.modules.notifications.pdf_store import read_mail_pdf

            mail_copy = read_mail_pdf(
                tenant_id=cert.tenant_id,
                kind="certificate",
                resource_id=cert.id,
            )
            if mail_copy is not None:
                content, _mail_name = mail_copy
                policy = await self.policies.get(cert.policy_id)
                try:
                    stored = store_certificate_pdf(
                        tenant_id=cert.tenant_id,
                        policy_id=policy.id,
                        certificate_id=cert.id,
                        content=content,
                    )
                    cert.local_file_path = stored.relative_path
                    cert.local_stored_at = datetime.now(UTC)
                    cert.content_sha256 = stored.sha256
                    cert.file_size_bytes = stored.size_bytes
                except ValueError:
                    pass
                return await _succeed(content, source=CertificateAccessSource.LOCAL)
        except Exception:
            pass

        url = cert.provider_cert_url or cert.storage_key
        payload = cert.provider_payload if isinstance(cert.provider_payload, dict) else {}

        if (not url or "example.local" in str(url)) and payload:
            candidate = _extract_cert_url(payload)
            if candidate:
                url = candidate
                cert.storage_key = url
                cert.provider_cert_url = url
                # Persist before Azure probe / raise so the next poll skips Definite
                await self.session.commit()

        # Prefer a still-valid Azure URL. Expired SAS tokens must fall through to
        # Definite regenerate — probing them forever surfaces a false "preparing" error.
        url_expired = bool(url) and _azure_sas_expired(str(url))
        if url and "example.local" not in str(url) and not url_expired:
            content = await _fetch_remote_pdf(str(url))
            if content is not None:
                policy = await self.policies.get(cert.policy_id)
                # Always (re)persist when the durable copy was missing — covers GCS
                # migration, ephemeral Cloud Run disks, and soft-deleted objects.
                try:
                    stored = store_certificate_pdf(
                        tenant_id=cert.tenant_id,
                        policy_id=policy.id,
                        certificate_id=cert.id,
                        content=content,
                    )
                    cert.local_file_path = stored.relative_path
                    cert.local_stored_at = datetime.now(UTC)
                    cert.content_sha256 = stored.sha256
                    cert.file_size_bytes = stored.size_bytes
                    await self._record_file_access(
                        cert,
                        access_kind=CertificateAccessKind.STORED,
                        source=CertificateAccessSource.SYSTEM,
                        metadata={
                            "bytes": stored.size_bytes,
                            "sha256": stored.sha256,
                            "repaired": True,
                        },
                    )
                except ValueError:
                    pass
                cert.provider_cert_url = str(url)
                cert.storage_key = str(url)
                return await _succeed(
                    content, source=CertificateAccessSource.REMOTE_PROVIDER
                )
            # Valid SAS but blob not ready yet — keep polling Azure, don't thrash Definite.
            await _fail(
                "Certificate PDF is still being prepared. Please wait a moment and try again.",
                retryable=True,
            )

        # No usable URL (missing or expired SAS) — refresh from Definite at most once / 30s
        last_refresh = payload.get("pdf_url_refreshed_at")
        now = datetime.now(UTC)
        can_refresh = True
        if isinstance(last_refresh, str) and not url_expired:
            try:
                prev = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
                can_refresh = (now - prev).total_seconds() >= 30
            except ValueError:
                can_refresh = True

        if not can_refresh:
            await _fail(
                "Certificate PDF is still being prepared. Please wait a moment and try again.",
                retryable=True,
            )

        policy = await self.policies.get(cert.policy_id)
        summary = policy.provider_payload_summary or {}
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
        if not proposal_ref or not note_oid:
            await _fail(
                "Certificate PDF is still being prepared. Please wait a moment and try again.",
                retryable=True,
            )

        # Prefer getPolicyDetails — may return CertUrl without re-issuing.
        try:
            from app.core.config import get_settings as _get_settings

            agent_code = (_get_settings().definite_assurance_agent_code or "").strip()
            details_remote = await self.provider.get_policy_details(
                {
                    "proposal": str(proposal_ref),
                    **({"agentCode": agent_code} if agent_code else {}),
                }
            )
            details_dict = details_remote if isinstance(details_remote, dict) else {}
            proposal_details = details_dict.get("proposalDetails")
            if isinstance(proposal_details, dict):
                for key in ("CertUrl", "certURL", "certUrl", "CertificateUrl", "pdfUrl"):
                    candidate = proposal_details.get(key)
                    if candidate and not _azure_sas_expired(str(candidate)):
                        content = await _fetch_remote_pdf(str(candidate))
                        if content is not None:
                            await self._try_persist_local_pdf(cert, policy, str(candidate))
                            cert.provider_cert_url = str(candidate)
                            cert.storage_key = str(candidate)
                            await self.session.commit()
                            return await _succeed(
                                content, source=CertificateAccessSource.REMOTE_PROVIDER
                            )
                        break
        except Exception:
            pass

        holder_oid = await self._resolve_policy_holder_oid(policy)
        holder_email = await self._resolve_policy_holder_email(policy)
        remote_dict = await self._generate_certificate_with_retry(
            proposal_ref=proposal_ref,
            note_oid=note_oid,
            policy=policy,
            cert_number=str(
                cert.external_certificate_ref or cert.certificate_number or ""
            ),
            holder_oid=holder_oid,
            holder_email=holder_email,
        )
        new_url = _extract_cert_url(remote_dict)

        if not _definite_cert_issued(remote_dict):
            # Persist cooldown + failure so we stop thrashing Definite and surface the error
            already_issued = bool(
                cert.external_certificate_ref
                or (isinstance(payload, dict) and payload.get("certNo"))
                or cert.status == CertificateStatus.GENERATED.value
            )
            cert.failure_message = _definite_error_message(
                remote_dict, for_refresh=already_issued
            )
            cert.provider_payload = {
                **payload,
                "pdf_url_refreshed_at": now.isoformat(),
                "last_generate_error": remote_dict,
            }
            await self.session.commit()
            await _fail(cert.failure_message, retryable=not already_issued)

        merged_payload = {**payload, **remote_dict, "pdf_url_refreshed_at": now.isoformat()}
        cert.provider_payload = merged_payload
        cert.failure_message = None
        if new_url:
            cert.storage_key = str(new_url)
            cert.provider_cert_url = str(new_url)
            cert.external_certificate_ref = str(
                _cert_number(remote_dict)
                or cert.external_certificate_ref
                or cert.certificate_number
            )
            cert.status = CertificateStatus.GENERATED.value

        # Commit before Azure check / raise — otherwise get_db rollback undoes the URL
        await self.session.commit()

        if new_url:
            # Definite often returns a SAS URL before Azure finishes writing the blob.
            ready = await _wait_for_remote_pdf(str(new_url), attempts=8)
            content = await _fetch_remote_pdf(str(new_url)) if ready else None
            if content is None:
                content = await _fetch_remote_pdf(str(new_url))
            if content is not None:
                await self._try_persist_local_pdf(cert, policy, str(new_url))
                return await _succeed(
                    content, source=CertificateAccessSource.REMOTE_PROVIDER
                )

        await _fail(
            "Certificate PDF is still being prepared. Please wait a moment and try again.",
            retryable=True,
        )
        raise AssertionError("unreachable")


async def _wait_for_remote_pdf(url: str, *, attempts: int = 8) -> bool:
    for attempt in range(attempts):
        content = await _fetch_remote_pdf(url)
        if content:
            return True
        await asyncio.sleep(min(1.25 * (attempt + 1), 6.0))
    return False


def _azure_sas_expired(url: str) -> bool:
    """True when an Azure Blob SAS ``se=`` expiry is present and already past."""
    try:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if "blob.core.windows.net" not in host and "azureedge.net" not in host:
            return False
        se = (parse_qs(parsed.query).get("se") or [None])[0]
        if not se:
            return False
        expiry = datetime.fromisoformat(str(se).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return datetime.now(UTC) >= expiry
    except Exception:
        return False


async def _fetch_remote_pdf(url: str) -> bytes | None:
    current = url
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=False) as client:
            for _ in range(4):
                if not certificate_fetch_allowed(current):
                    return None
                response = await client.get(current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current = str(httpx.URL(current).join(location))
                    continue
                if response.status_code != 200:
                    return None
                body = response.content or b""
                content_type = (response.headers.get("content-type") or "").lower()
                if body.startswith(b"%PDF"):
                    return body
                if (
                    "pdf" in content_type
                    and b"BlobNotFound" not in body
                    and b"<Error>" not in body[:200]
                ):
                    return body
                return None
    except Exception:
        return None
    return None


def certificate_fetch_allowed(url: str, *, allowed_hosts: str | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    raw = allowed_hosts if allowed_hosts is not None else get_settings().certificate_download_hosts
    allowed = [h.strip().lower().lstrip(".") for h in raw.split(",") if h.strip()]
    return any(host == pattern or host.endswith("." + pattern) for pattern in allowed)
