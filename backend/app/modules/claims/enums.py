"""Claims lifecycle, authority, and collaboration enums."""

from enum import StrEnum


class ClaimStatus(StrEnum):
    CLAIM_DRAFT = "CLAIM_DRAFT"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED"
    VETTING = "VETTING"
    ADDITIONAL_INFORMATION_REQUIRED = "ADDITIONAL_INFORMATION_REQUIRED"
    VETTING_PASSED = "VETTING_PASSED"
    VETTING_FAILED = "VETTING_FAILED"
    SENT_TO_DEFINITE = "SENT_TO_DEFINITE"
    DEFINITE_REVIEW = "DEFINITE_REVIEW"
    DEFINITE_APPROVED = "DEFINITE_APPROVED"
    DEFINITE_REJECTED = "DEFINITE_REJECTED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_AUTHORIZATION = "PAYMENT_AUTHORIZATION"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"
    CLIENT_NOTIFIED = "CLIENT_NOTIFIED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    WITHDRAWN = "WITHDRAWN"


class ClaimType(StrEnum):
    MOTOR = "MOTOR"
    MEDICAL = "MEDICAL"
    PROPERTY = "PROPERTY"
    LIABILITY = "LIABILITY"
    OTHER = "OTHER"


class ClaimChannel(StrEnum):
    STAFF = "STAFF"
    CLIENT = "CLIENT"
    GUEST = "GUEST"
    USSD = "USSD"


class VettingDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"


class Duty(StrEnum):
    VET = "VET"
    APPROVE = "APPROVE"
    AUTHORIZE_PAYMENT = "AUTHORIZE_PAYMENT"
    EXECUTE_PAYMENT = "EXECUTE_PAYMENT"
    MARK_PAYMENT_SUCCESS = "MARK_PAYMENT_SUCCESS"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RECOMMENDED = "RECOMMENDED"


class AmendmentStatus(StrEnum):
    REQUESTED = "REQUESTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PaymentInstructionStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BeneficiaryType(StrEnum):
    CLIENT = "CLIENT"
    STAR_SERVE = "STAR_SERVE"


class FollowupType(StrEnum):
    CLIENT_INFORMATION = "CLIENT_INFORMATION"
    DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
    MEDICAL_INFORMATION = "MEDICAL_INFORMATION"
    POLICE_DOCUMENT = "POLICE_DOCUMENT"
    PAYMENT_INFORMATION = "PAYMENT_INFORMATION"
    INTERNAL_REVIEW = "INTERNAL_REVIEW"
    OTHER = "OTHER"


class FollowupStatus(StrEnum):
    OPEN = "OPEN"
    PENDING_CLIENT = "PENDING_CLIENT"
    PENDING_INTERNAL = "PENDING_INTERNAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NoteVisibility(StrEnum):
    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"


class ExternalReviewStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ExternalReviewProvider(StrEnum):
    DEFINITE = "DEFINITE"


class ClaimEventActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    DEFINITE = "DEFINITE"
    PAYMENT_PROVIDER = "PAYMENT_PROVIDER"


class AssignmentReason(StrEnum):
    CREATED = "CREATED"
    MANUAL = "MANUAL"
    ESCALATED = "ESCALATED"
    REASSIGNED = "REASSIGNED"
    OVERRIDE = "OVERRIDE"


class DocumentKind(StrEnum):
    POLICE = "POLICE"
    MEDICAL = "MEDICAL"
    VEHICLE = "VEHICLE"
    IDENTITY = "IDENTITY"
    POLICY = "POLICY"
    OTHER = "OTHER"


TERMINAL_STATUSES = frozenset(
    {
        ClaimStatus.VETTING_FAILED.value,
        ClaimStatus.DEFINITE_REJECTED.value,
        ClaimStatus.REJECTED.value,
        ClaimStatus.CANCELLED.value,
        ClaimStatus.WITHDRAWN.value,
        ClaimStatus.CLOSED.value,
    }
)

FINANCIAL_LOCK_STATUSES = frozenset(
    {
        ClaimStatus.DEFINITE_APPROVED.value,
        ClaimStatus.PAYMENT_PENDING.value,
        ClaimStatus.PAYMENT_AUTHORIZATION.value,
        ClaimStatus.PAYMENT_AUTHORIZED.value,
        ClaimStatus.PAYMENT_PROCESSING.value,
        ClaimStatus.PAYMENT_COMPLETED.value,
        ClaimStatus.CLIENT_NOTIFIED.value,
        ClaimStatus.CLOSED.value,
    }
)

CORE_FACT_LOCK_STATUSES = frozenset(
    {
        ClaimStatus.VETTING_PASSED.value,
        ClaimStatus.SENT_TO_DEFINITE.value,
        ClaimStatus.DEFINITE_REVIEW.value,
        ClaimStatus.DEFINITE_APPROVED.value,
        ClaimStatus.DEFINITE_REJECTED.value,
        ClaimStatus.PAYMENT_PENDING.value,
        ClaimStatus.PAYMENT_AUTHORIZATION.value,
        ClaimStatus.PAYMENT_AUTHORIZED.value,
        ClaimStatus.PAYMENT_PROCESSING.value,
        ClaimStatus.PAYMENT_COMPLETED.value,
        ClaimStatus.PAYMENT_FAILED.value,
        ClaimStatus.PAYMENT_REVIEW.value,
        ClaimStatus.CLIENT_NOTIFIED.value,
        ClaimStatus.CLOSED.value,
        ClaimStatus.REJECTED.value,
        ClaimStatus.VETTING_FAILED.value,
    }
)
