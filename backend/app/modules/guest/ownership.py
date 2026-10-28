"""Guest resource ownership — session + origin, never client-supplied IDs alone."""

from __future__ import annotations

from uuid import UUID

from app.core.exceptions import AuthorizationError
from app.core.security.context import SecurityContext
from app.core.security.guest_capabilities import GuestContext
from app.modules.customers.enums import CustomerOrigin
from app.modules.customers.models import Customer
from app.modules.policies.models import Policy

GUEST_IDENTITY_ERROR = (
    "We could not start this quote. Check your details or contact the agency."
)
GUEST_RESOURCE_ERROR = "Guest session cannot use this resource"


def customer_owned_by_guest(customer: Customer, guest: GuestContext) -> bool:
    return (
        customer.origin == CustomerOrigin.GUEST.value
        and customer.guest_session_id == guest.session_id
    )


def require_owned_customer(customer: Customer, guest: GuestContext) -> None:
    if not customer_owned_by_guest(customer, guest):
        raise AuthorizationError(GUEST_RESOURCE_ERROR)


def require_owned_customer_ctx(ctx: SecurityContext, customer: Customer) -> None:
    """Fail closed when a guest execution adapter touches a staff (or other) customer."""
    if not ctx.is_guest:
        return
    if (
        customer.origin != CustomerOrigin.GUEST.value
        or customer.guest_session_id != ctx.session_id
    ):
        raise AuthorizationError(GUEST_RESOURCE_ERROR)


def require_owned_policy_ctx(ctx: SecurityContext, policy: Policy, customer: Customer) -> None:
    if not ctx.is_guest:
        return
    if policy.customer_id is None or policy.customer_id != customer.id:
        raise AuthorizationError(GUEST_RESOURCE_ERROR)
    require_owned_customer_ctx(ctx, customer)


def guest_session_matches(guest: GuestContext, guest_session_id: UUID | None) -> bool:
    return guest_session_id is not None and guest_session_id == guest.session_id
