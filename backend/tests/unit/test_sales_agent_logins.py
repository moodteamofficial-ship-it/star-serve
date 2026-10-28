"""Sales Agent logins: restricted role, own-rows scoping, and approval-gated sign-in."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext
from app.modules.customers.repository import CustomerRepository
from app.modules.intermediaries import login as login_module
from app.modules.intermediaries.schemas import IntermediaryCreateRequest
from app.modules.overview.service import _OVERVIEW_SQL_AGENT, _overview_table_predicate
from app.modules.payments.repository import PaymentRepository
from app.modules.policies.repository import PolicyRepository
from app.modules.roles.permissions_catalog import (
    SALES_AGENT_PERMISSIONS,
    SALES_AGENT_ROLE_CODE,
    SYSTEM_ROLES,
)


def _ctx(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "agent@example.com",
        "role_id": uuid4(),
        "role_code": SALES_AGENT_ROLE_CODE,
        "permissions": set(SALES_AGENT_PERMISSIONS),
        "branch_scope": BranchScope.ALL_TENANT,
    }
    values.update(overrides)
    return SecurityContext(**values)


def _sql(stmt) -> str:
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


def test_sales_agent_role_is_seeded_with_only_sales_and_claims_rights() -> None:
    role = next(r for r in SYSTEM_ROLES if r["code"] == SALES_AGENT_ROLE_CODE)
    assert set(role["permissions"]) == {
        "customer:read",
        "policy:read",
        "payment:read",
        "claim:create",
        "claim:read",
        "claim:update",
        "claim:document:upload",
        "claim:document:download",
    }
    forbidden = ("proposal:", "agent:", "user:", "role:")
    assert not any(p.startswith(forbidden) for p in role["permissions"])


def test_agent_sees_only_their_policies_payments_and_customers() -> None:
    agent_id = uuid4()
    ctx = _ctx(agent_intermediary_id=agent_id)
    policy_sql = _sql(PolicyRepository(None, ctx)._base_select())  # type: ignore[arg-type]
    payment_sql = _sql(PaymentRepository(None, ctx)._count_select())  # type: ignore[arg-type]
    customer_sql = _sql(CustomerRepository(None, ctx)._active_select())  # type: ignore[arg-type]

    assert f"policies.intermediary_id = '{agent_id}'" in policy_sql
    assert "payments.policy_id in (select policies.id" in payment_sql
    assert f"customers.referred_by_intermediary_id = '{agent_id}'" in customer_sql
    assert "exists (select" in customer_sql


def test_unlinked_sales_agent_sees_nothing() -> None:
    ctx = _ctx(agent_intermediary_id=None)
    for repo in (PolicyRepository, PaymentRepository, CustomerRepository):
        assert "false" in _sql(repo(None, ctx)._base_select())  # type: ignore[arg-type]


def test_staff_queries_are_not_agent_filtered() -> None:
    ctx = _ctx(role_code="claims_officer", agent_intermediary_id=uuid4())
    sql = _sql(PolicyRepository(None, ctx)._base_select())  # type: ignore[arg-type]
    where = sql.split("where", 1)[1]
    assert "policies.intermediary_id =" not in where


def test_platform_admin_with_agent_role_code_is_not_restricted() -> None:
    ctx = _ctx(is_platform_admin=True)
    assert ctx.is_sales_agent is False


def test_overview_agent_sql_pins_every_sales_table() -> None:
    assert "intermediary_id = cast(:agent_id as uuid)" in _OVERVIEW_SQL_AGENT.lower()
    assert _overview_table_predicate("certificates", BranchScope.ALL_TENANT, agent=True).endswith(
        "AND FALSE"
    )
    claims = _overview_table_predicate("claims", BranchScope.ALL_TENANT, agent=True)
    assert "created_by_user_id = CAST(:user_id AS uuid)" in claims


def test_create_request_password_is_optional_but_validated() -> None:
    base = {
        "name": "Jane Agent",
        "email": "jane@example.com",
        "phone": "+254700000000",
        "identification": "12345678",
    }
    secret = "s3cret-pass"  # noqa: S105
    assert IntermediaryCreateRequest(**base).password is None
    assert IntermediaryCreateRequest(**base, password=secret).password == secret
    with pytest.raises(ValidationError):
        IntermediaryCreateRequest(**base, password=secret[:3])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_status", "user_status", "expected", "revoked"),
    [
        ("APPROVED", "PENDING", "ACTIVE", False),
        ("SUSPENDED", "ACTIVE", "DISABLED", True),
        ("PENDING", "ACTIVE", "PENDING", True),
        ("APPROVED", "ACTIVE", "ACTIVE", False),
    ],
)
async def test_login_follows_agent_approval(
    monkeypatch: pytest.MonkeyPatch,
    agent_status: str,
    user_status: str,
    expected: str,
    revoked: bool,
) -> None:
    async def _noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(login_module, "set_rls_bypass", _noop)
    monkeypatch.setattr(login_module, "set_auth_write_gate", _noop)

    user = SimpleNamespace(
        id=uuid4(), status=user_status, locked_until=None, failed_login_attempts=2
    )
    revoked_ids: list = []

    async def _flush() -> None:
        return None

    async def _revoke(user_id, **kwargs) -> None:
        revoked_ids.append(user_id)

    service = login_module.AgentLoginService.__new__(login_module.AgentLoginService)
    service.session = SimpleNamespace(flush=_flush)
    service.ctx = SimpleNamespace(user_id=uuid4())
    service._actor_id = service.ctx.user_id
    service.auth = SimpleNamespace(revoke_all_sessions=_revoke)

    async def _linked(row):
        return user

    monkeypatch.setattr(service, "_linked_user", _linked)
    await service.sync_status(SimpleNamespace(status=agent_status, user_id=user.id))

    assert user.status == expected
    assert bool(revoked_ids) is revoked
