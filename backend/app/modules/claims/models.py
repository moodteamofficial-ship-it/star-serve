"""Claims domain models — tenant-owned, versioned, assignment-aware."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.claims.enums import (
    AssignmentReason,
    BeneficiaryType,
    ClaimChannel,
    ClaimStatus,
    ClaimType,
    DocumentKind,
    ExternalReviewProvider,
    ExternalReviewStatus,
    FollowupStatus,
    FollowupType,
    NoteVisibility,
    PaymentInstructionStatus,
    VettingDecision,
)


class Claim(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("tenant_id", "claim_number", name="uq_claims_tenant_number"),
        CheckConstraint("claimed_amount >= 0", name="claimed_amount_nonneg"),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0",
            name="approved_amount_nonneg",
        ),
        CheckConstraint("version >= 1", name="claim_version_positive"),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_to_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    guest_session_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    claim_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ClaimType.MOTOR.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(48), nullable=False, default=ClaimStatus.CLAIM_DRAFT.value, index=True
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ClaimChannel.STAFF.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    incident_date: Mapped[date | None] = mapped_column(Date)
    incident_time: Mapped[str | None] = mapped_column(String(16))
    incident_location: Mapped[str | None] = mapped_column(String(255))
    incident_description: Mapped[str | None] = mapped_column(Text)
    police_abstract_number: Mapped[str | None] = mapped_column(String(64))

    vehicle_registration: Mapped[str | None] = mapped_column(String(32), index=True)
    vehicle_make: Mapped[str | None] = mapped_column(String(64))
    vehicle_model: Mapped[str | None] = mapped_column(String(128))
    chassis_number: Mapped[str | None] = mapped_column(String(64))

    driver_name: Mapped[str | None] = mapped_column(String(255))
    driver_license_number: Mapped[str | None] = mapped_column(String(64))

    damage_description: Mapped[str | None] = mapped_column(Text)
    injury_summary: Mapped[str | None] = mapped_column(Text)
    medical_notes: Mapped[str | None] = mapped_column(Text)
    risk_assessment: Mapped[str | None] = mapped_column(Text)

    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    beneficiary_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=BeneficiaryType.CLIENT.value
    )
    beneficiary_reference: Mapped[str | None] = mapped_column(String(128))

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64))


class ClaimAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_assignments"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_to_user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssignmentReason.MANUAL.value
    )
    note: Mapped[str | None] = mapped_column(String(512))


class ClaimVetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_vettings"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_to_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    required_documents: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    checklist: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class ClaimExternalReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_external_reviews"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_reference",
            name="uq_claim_external_reviews_ref",
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExternalReviewProvider.DEFINITE.value
    )
    external_reference: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExternalReviewStatus.PENDING.value, index=True
    )
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(32))
    response_payload_reference: Mapped[str | None] = mapped_column(String(128))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class ClaimApproval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_approvals"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approver_user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    amendment_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claim_amendments.id", ondelete="SET NULL")
    )


class ApprovalPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "approval_policies"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    minimum_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    maximum_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    claim_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ClaimType.MOTOR.value
    )
    requires_second_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    second_approval_above: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class SegregationPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "segregation_policies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "left_duty",
            "right_duty",
            name="uq_segregation_policies_pair",
        ),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    left_duty: Mapped[str] = mapped_column(String(48), nullable=False)
    right_duty: Mapped[str] = mapped_column(String(48), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ClaimDutyAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Who performed a segregation-of-duties action on a claim."""

    __tablename__ = "claim_duty_actions"
    __table_args__ = (
        UniqueConstraint("claim_id", "duty", "user_id", name="uq_claim_duty_actions_user"),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    duty: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    user_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class ClaimPayment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_claim_payments_idempotency"),
        CheckConstraint("amount > 0", name="claim_payment_amount_positive"),
    )

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    beneficiary_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=BeneficiaryType.CLIENT.value
    )
    beneficiary_reference: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KES")
    payment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PaymentInstructionStatus.DRAFT.value,
        index=True,
    )
    authorized_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    executed_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    provider_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClaimAmendment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_amendments"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED")
    reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClaimFollowup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_followups"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    followup_type: Mapped[str] = mapped_column(
        String(48), nullable=False, default=FollowupType.OTHER.value
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    requested_from: Mapped[str | None] = mapped_column(String(128))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FollowupStatus.OPEN.value, index=True
    )
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_to_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ClaimNote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_notes"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default=NoteVisibility.INTERNAL.value, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ClaimDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_documents"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentKind.OTHER.value
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ClaimDocumentAccess(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_document_accesses"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    access_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)


class ClaimEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only claim timeline. Mutations are rejected by a database trigger."""

    __tablename__ = "claim_events"

    tenant_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(64))
    actor_display_name: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(48))
    new_state: Mapped[str | None] = mapped_column(String(48))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class ClaimWebhookReceipt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_webhook_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "nonce", name="uq_claim_webhook_receipts_nonce"),
    )

    tenant_id: Mapped[Any | None] = mapped_column(UUID(as_uuid=True), index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_header: Mapped[str | None] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    claim_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL")
    )
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="ACCEPTED")
    detail: Mapped[str | None] = mapped_column(String(255))
