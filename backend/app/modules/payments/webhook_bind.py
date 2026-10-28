"""Webhook identity and outcome policy.

A callback URL token (or any other request authenticator) only answers *which*
payment the caller is talking about. It never answers whether money moved.

Providers must mark which identifier they actually authenticated. ``apply_webhook``
loads the row from that identifier only — never from an unsigned CheckoutRequestID.
Terminal failure requires an authenticated outcome so a leaked URL cannot
poison-fail a pending STK.
"""

from __future__ import annotations

import hmac

from app.core.exceptions import AuthenticationError
from app.integrations.payments.ports import WebhookVerificationResult
from app.modules.payments.models import Payment
from app.modules.policies.enums import PolicyStatus

IDENTITY_REFERENCE = "reference"
IDENTITY_CHECKOUT = "checkout"

# A *new* settlement may only attach to a policy still awaiting payment.
# ACTIVE / PENDING_CERTIFICATE mean another payment already won.
_POLICY_ACCEPTS_SETTLEMENT = {
    PolicyStatus.PENDING_PAYMENT.value,
}


def authenticated_payment_lookup(
    verified: WebhookVerificationResult,
) -> tuple[str, str]:
    """Return the only identifier that may be used to load a payment."""
    kind = (verified.identity_kind or IDENTITY_REFERENCE).strip()
    if kind == IDENTITY_CHECKOUT:
        value = (verified.checkout_id or "").strip()
        if not value:
            raise AuthenticationError("Webhook missing authenticated checkout id")
        return IDENTITY_CHECKOUT, value
    value = (verified.reference or "").strip()
    if not value:
        raise AuthenticationError("Webhook missing authenticated payment reference")
    return IDENTITY_REFERENCE, value


def assert_webhook_bound_to_payment(
    payment: Payment,
    verified: WebhookVerificationResult,
    *,
    method: str,
) -> None:
    """Bind a verified callback to the payment it authenticated."""
    if method and payment.method != method:
        raise AuthenticationError("Webhook method does not match payment")
    claimed_ref = (verified.reference or "").strip()
    if claimed_ref and claimed_ref != payment.reference:
        raise AuthenticationError("Webhook reference does not match payment")
    stored = (payment.provider_checkout_id or "").strip()
    claimed = (verified.checkout_id or "").strip()
    if stored and claimed and not hmac.compare_digest(stored, claimed):
        raise AuthenticationError("Webhook checkout id does not match payment")
    if verified.success and not verified.outcome_authenticated:
        if not stored or not claimed:
            raise AuthenticationError("Unsigned success requires the stored checkout id")


def assert_policy_accepts_settlement(policy, *, payment_tenant_id) -> None:
    if policy is None:
        raise AuthenticationError("Webhook payment has no policy")
    policy_tenant = getattr(policy, "tenant_id", None)
    if policy_tenant is not None and policy_tenant != payment_tenant_id:
        raise AuthenticationError("Webhook policy tenant mismatch")
    status = getattr(policy, "status", None)
    if status not in _POLICY_ACCEPTS_SETTLEMENT:
        raise AuthenticationError("Policy cannot accept settlement")


def may_apply_success(verified: WebhookVerificationResult) -> bool:
    return bool(verified.success) and (
        verified.outcome_authenticated or bool((verified.checkout_id or "").strip())
    )


def may_apply_failure(verified: WebhookVerificationResult) -> bool:
    """Unsigned ResultCode values are claims, not facts."""
    return (not verified.success) and verified.outcome_authenticated
