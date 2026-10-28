"""Phase 5 — empty branch assignments are not tenant-wide access."""

from __future__ import annotations

import inspect
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.core.database.repository import TenantAwareRepository
from app.core.dependencies.auth import get_current_context
from app.core.security.branch_scope import BranchScope, resolve_branch_scope
from app.core.security.context import SecurityContext
from app.modules.customers.models import Customer
from app.modules.payments.router import _webhook_security_context
from app.modules.roles import permissions_catalog, service as roles_service


def _ctx(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "a@agency.local",
        "role_id": uuid4(),
        "role_code": "agent",
        "permissions": {"customer:read"},
    }
    values.update(overrides)
    return SecurityContext(**values)


class _CustomerRepo(TenantAwareRepository[Customer]):
    model = Customer


def _sql(ctx: SecurityContext) -> str:
    stmt = _CustomerRepo(None, ctx)._base_select()  # type: ignore[arg-type]
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled).lower()


def test_empty_assignments_resolve_to_none() -> None:
    scope, ids = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"customer:read", "user:manage"},
        assigned_branch_ids=set(),
    )
    assert scope is BranchScope.NONE
    assert ids == set()


def test_branch_all_is_explicit_tenant_wide() -> None:
    assigned = {uuid4()}
    scope, ids = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"customer:read", "branch:all"},
        assigned_branch_ids=assigned,
    )
    assert scope is BranchScope.ALL_TENANT
    assert ids == set()


def test_wildcard_does_not_imply_tenant_wide_branches() -> None:
    wildcard, _ = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"*:*"},
        assigned_branch_ids=set(),
    )
    platform, _ = resolve_branch_scope(
        is_platform_admin=True,
        permissions=set(),
        assigned_branch_ids=set(),
    )
    assert wildcard is BranchScope.NONE
    assert platform is BranchScope.ALL_TENANT


def test_transactional_branch_never_asks_to_select() -> None:
    """Kit / OTP mail must not raise 'Select an authorized branch'."""
    import asyncio
    from unittest.mock import AsyncMock

    import app.core.security.branch_scope as bs
    from app.core.security.branch_scope import resolve_transactional_branch

    tenant = uuid4()
    b1, b2, dead = uuid4(), uuid4(), uuid4()

    async def _load(_session, *, tenant_id, branch_id):
        return object() if branch_id in {b1, b2} else None

    orig_load = bs.load_tenant_branch
    orig_first = bs.first_active_tenant_branch_id
    bs.load_tenant_branch = AsyncMock(side_effect=_load)
    bs.first_active_tenant_branch_id = AsyncMock(return_value=b1)
    try:
        ctx = _ctx(
            tenant_id=tenant,
            branch_scope=BranchScope.ASSIGNED,
            branch_ids={b1, b2},
            home_branch_id=b2,
        )

        async def _run():
            assert await resolve_transactional_branch(ctx, None, None) == b2
            assert await resolve_transactional_branch(ctx, None, b1) == b1
            assert await resolve_transactional_branch(ctx, None, dead) == b2

        asyncio.run(_run())
    finally:
        bs.load_tenant_branch = orig_load
        bs.first_active_tenant_branch_id = orig_first


def test_assigned_ids_are_not_inferred_from_empty_set() -> None:
    branch = uuid4()
    scope, ids = resolve_branch_scope(
        is_platform_admin=False,
        permissions={"customer:read"},
        assigned_branch_ids={branch},
    )
    assert scope is BranchScope.ASSIGNED
    assert ids == {branch}


def test_none_scope_fails_closed_on_branch_tables() -> None:
    sql = _sql(_ctx(branch_scope=BranchScope.NONE, branch_ids=set()))
    assert "false" in sql
    assert "customers.branch_id in" not in sql


def test_user_manager_without_branch_all_is_not_tenant_wide() -> None:
    ctx = _ctx(
        permissions={"user:manage", "user:write", "role:manage", "customer:read"},
        branch_scope=BranchScope.NONE,
        branch_ids=set(),
    )
    assert ctx.can_manage_users() is True
    sql = _sql(ctx)
    assert "false" in sql


def test_assigned_scope_filters_to_those_branches() -> None:
    branch = uuid4()
    sql = _sql(_ctx(branch_scope=BranchScope.ASSIGNED, branch_ids={branch}))
    assert str(branch) in sql
    assert "customers.branch_id" in sql
    assert "false" not in sql
    assert "is not null" in sql


def test_apply_branch_predicate_never_treats_null_as_all() -> None:
    from sqlalchemy import select

    from app.core.security.branch_scope import apply_branch_predicate

    branch = uuid4()
    assigned = apply_branch_predicate(
        select(Customer.id),
        Customer,
        _ctx(branch_scope=BranchScope.ASSIGNED, branch_ids={branch}),
    )
    sql = str(
        assigned.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()
    assert str(branch) in sql
    assert "is not null" in sql or "is not null" in sql.replace("\n", " ")
    none_sql = str(
        apply_branch_predicate(
            select(Customer.id),
            Customer,
            _ctx(branch_scope=BranchScope.NONE, branch_ids=set()),
        ).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()
    assert "false" in none_sql


def test_assigned_scope_does_not_treat_null_as_shared() -> None:
    from app.core.database.repository import TenantAwareRepository

    source = inspect.getsource(TenantAwareRepository._apply_branch_scope)
    assert "branch_col.is_(None)" not in source
    assert "branch_col.in_" in source
    assert "branch_col.is_not(None)" in source


def test_all_tenant_and_guest_skip_branch_filter() -> None:
    admin_where = _sql(_ctx(branch_scope=BranchScope.ALL_TENANT, branch_ids=set())).split(
        "where", 1
    )[-1]
    guest_where = _sql(
        _ctx(is_guest=True, branch_scope=BranchScope.NONE, branch_ids=set(), permissions=set())
    ).split("where", 1)[-1]
    assert "branch_id" not in admin_where
    assert "false" not in admin_where
    assert "branch_id" not in guest_where
    assert "false" not in guest_where


def test_auth_uses_live_branches_not_jwt_bids() -> None:
    source = inspect.getsource(get_current_context)
    assert "live_branches" in source
    assert "resolve_branch_scope" in source
    assert 'payload.get("bids")' not in source
    assert "for raw in payload.get(\"bids\")" not in source


def test_home_branch_is_part_of_live_assignments() -> None:
    from app.core.dependencies import auth as auth_mod

    bind_sql = str(auth_mod._AUTH_BIND_AND_CHECK)
    loader = inspect.getsource(roles_service.load_user_branch_ids)
    assert "u.branch_id" in bind_sql
    assert "live_branches" in bind_sql
    assert "user_branches" in bind_sql
    assert "User.branch_id" in loader
    assert "UserBranch" in loader


def test_tenant_wide_roles_have_branch_all_agents_do_not() -> None:
    assert "branch:all" in permissions_catalog.FINANCE_PERMISSIONS
    assert "branch:all" in permissions_catalog.AUDITOR_PERMISSIONS
    assert "branch:all" in permissions_catalog.AGENCY_ADMIN_PERMISSIONS
    underwriter = next(
        spec["permissions"]
        for spec in permissions_catalog.SYSTEM_ROLES
        if spec["code"] == "underwriter"
    )
    branch_manager = next(
        spec["permissions"]
        for spec in permissions_catalog.SYSTEM_ROLES
        if spec["code"] == "branch_manager"
    )
    assert "branch:all" in underwriter
    assert "branch:all" not in permissions_catalog.AGENT_PERMISSIONS
    assert "branch:all" not in branch_manager


def test_assigned_notifications_exclude_other_and_null_branches() -> None:
    from app.modules.notifications.models import Notification

    class _NotificationRepo(TenantAwareRepository[Notification]):
        model = Notification

    branch = uuid4()
    ctx = _ctx(branch_scope=BranchScope.ASSIGNED, branch_ids={branch})
    compiled = _NotificationRepo(None, ctx)._base_select().compile(  # type: ignore[arg-type]
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = str(compiled).lower()
    assert str(branch) in sql
    assert "notifications.branch_id" in sql
    assert "is not null" in sql
    assert "false" not in sql


def test_webhook_context_is_not_branch_filtered() -> None:
    ctx = _webhook_security_context()
    assert ctx.branch_scope is BranchScope.ALL_TENANT
    where = _sql(ctx).split("where", 1)[-1]
    assert "branch_id" not in where
    assert "false" not in where
