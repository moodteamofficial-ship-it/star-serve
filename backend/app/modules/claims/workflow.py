"""Backend-owned claim state machine. Status is never taken from the client."""

from __future__ import annotations

from app.core.exceptions import ConflictError
from app.modules.claims.enums import ClaimStatus

# Explicit allowed edges. Anything else is a 409 — including admin PATCH attempts.
TRANSITIONS: dict[str, frozenset[str]] = {
    ClaimStatus.CLAIM_DRAFT.value: frozenset(
        {
            ClaimStatus.CLAIM_SUBMITTED.value,
            ClaimStatus.CANCELLED.value,
            ClaimStatus.WITHDRAWN.value,
        }
    ),
    ClaimStatus.CLAIM_SUBMITTED.value: frozenset(
        {
            ClaimStatus.VETTING.value,
            ClaimStatus.CANCELLED.value,
            ClaimStatus.WITHDRAWN.value,
        }
    ),
    ClaimStatus.VETTING.value: frozenset(
        {
            ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
            ClaimStatus.VETTING_PASSED.value,
            ClaimStatus.VETTING_FAILED.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value: frozenset(
        {
            ClaimStatus.VETTING.value,
            ClaimStatus.WITHDRAWN.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.VETTING_PASSED.value: frozenset(
        {
            ClaimStatus.SENT_TO_DEFINITE.value,
            ClaimStatus.REJECTED.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.SENT_TO_DEFINITE.value: frozenset(
        {
            ClaimStatus.DEFINITE_REVIEW.value,
            ClaimStatus.DEFINITE_REJECTED.value,
        }
    ),
    ClaimStatus.DEFINITE_REVIEW.value: frozenset(
        {
            ClaimStatus.DEFINITE_APPROVED.value,
            ClaimStatus.DEFINITE_REJECTED.value,
        }
    ),
    ClaimStatus.DEFINITE_APPROVED.value: frozenset({ClaimStatus.PAYMENT_PENDING.value}),
    ClaimStatus.PAYMENT_PENDING.value: frozenset(
        {
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.PAYMENT_AUTHORIZATION.value: frozenset(
        {
            ClaimStatus.PAYMENT_AUTHORIZED.value,
            ClaimStatus.PAYMENT_PENDING.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.PAYMENT_AUTHORIZED.value: frozenset({ClaimStatus.PAYMENT_PROCESSING.value}),
    ClaimStatus.PAYMENT_PROCESSING.value: frozenset(
        {
            ClaimStatus.PAYMENT_COMPLETED.value,
            ClaimStatus.PAYMENT_FAILED.value,
        }
    ),
    ClaimStatus.PAYMENT_FAILED.value: frozenset({ClaimStatus.PAYMENT_REVIEW.value}),
    ClaimStatus.PAYMENT_REVIEW.value: frozenset(
        {
            ClaimStatus.PAYMENT_AUTHORIZATION.value,
            ClaimStatus.PAYMENT_PROCESSING.value,
            ClaimStatus.CANCELLED.value,
        }
    ),
    ClaimStatus.PAYMENT_COMPLETED.value: frozenset({ClaimStatus.CLIENT_NOTIFIED.value}),
    ClaimStatus.CLIENT_NOTIFIED.value: frozenset({ClaimStatus.CLOSED.value}),
}

# Integration / system-only edges. Staff tokens cannot drive these even with
# override_workflow — they require the dedicated integration path.
SYSTEM_ONLY_TARGETS = frozenset(
    {
        ClaimStatus.DEFINITE_REVIEW.value,
        ClaimStatus.DEFINITE_APPROVED.value,
        ClaimStatus.DEFINITE_REJECTED.value,
        ClaimStatus.PAYMENT_COMPLETED.value,
        ClaimStatus.PAYMENT_FAILED.value,
    }
)

STAFF_ACTION_TARGETS: dict[str, str] = {
    "submit": ClaimStatus.CLAIM_SUBMITTED.value,
    "start_vetting": ClaimStatus.VETTING.value,
    "request_information": ClaimStatus.ADDITIONAL_INFORMATION_REQUIRED.value,
    "resume_vetting": ClaimStatus.VETTING.value,
    "pass_vetting": ClaimStatus.VETTING_PASSED.value,
    "fail_vetting": ClaimStatus.VETTING_FAILED.value,
    "forward_to_definite": ClaimStatus.SENT_TO_DEFINITE.value,
    "reject": ClaimStatus.REJECTED.value,
    "withdraw": ClaimStatus.WITHDRAWN.value,
    "cancel": ClaimStatus.CANCELLED.value,
    "request_payment": ClaimStatus.PAYMENT_AUTHORIZATION.value,
    "authorize_payment": ClaimStatus.PAYMENT_AUTHORIZED.value,
    "return_payment": ClaimStatus.PAYMENT_PENDING.value,
    "execute_payment": ClaimStatus.PAYMENT_PROCESSING.value,
    "retry_payment": ClaimStatus.PAYMENT_PROCESSING.value,
    "review_payment": ClaimStatus.PAYMENT_REVIEW.value,
    "notify_client": ClaimStatus.CLIENT_NOTIFIED.value,
    "close": ClaimStatus.CLOSED.value,
}


def assert_transition(current: str, target: str, *, system: bool = False) -> None:
    allowed = TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ConflictError(f"Claim cannot move from {current} to {target}")
    if target in SYSTEM_ONLY_TARGETS and not system:
        raise ConflictError("That status can only be set by an authorized integration")


def next_status_for_action(action: str) -> str:
    try:
        return STAFF_ACTION_TARGETS[action]
    except KeyError as exc:
        raise ConflictError("Unknown claim action") from exc
