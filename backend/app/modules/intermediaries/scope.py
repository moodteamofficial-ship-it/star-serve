"""Row filters for Sales Agent logins: only the agent's own sales and customers.

Every helper is fail-closed: a sales agent without a linked, approved
intermediary matches nothing.
"""

from typing import Any

from sqlalchemy import ColumnElement, Select, exists, false, or_, select

from app.core.security.context import SecurityContext


def agent_policy_ids(ctx: SecurityContext) -> Select[Any]:
    from app.modules.policies.models import Policy

    stmt = select(Policy.id).where(Policy.tenant_id == ctx.tenant_id)
    if ctx.agent_intermediary_id is None:
        return stmt.where(false())
    return stmt.where(Policy.intermediary_id == ctx.agent_intermediary_id)


def policy_predicate(ctx: SecurityContext) -> ColumnElement[bool]:
    from app.modules.policies.models import Policy

    if ctx.agent_intermediary_id is None:
        return false()
    return Policy.intermediary_id == ctx.agent_intermediary_id


def customer_predicate(ctx: SecurityContext) -> ColumnElement[bool]:
    """Customers the agent sold a policy to, or who signed up with the agent's code."""
    from app.modules.customers.models import Customer
    from app.modules.policies.models import Policy

    if ctx.agent_intermediary_id is None:
        return false()
    sold = exists().where(
        Policy.customer_id == Customer.id,
        Policy.tenant_id == ctx.tenant_id,
        Policy.intermediary_id == ctx.agent_intermediary_id,
    )
    return or_(Customer.referred_by_intermediary_id == ctx.agent_intermediary_id, sold)


def payment_predicate(ctx: SecurityContext) -> ColumnElement[bool]:
    from app.modules.payments.models import Payment

    if ctx.agent_intermediary_id is None:
        return false()
    return Payment.policy_id.in_(agent_policy_ids(ctx))
