"""Unit tests — password hashing and security context."""

from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, TenantAccessError, TenantSuspendedError
from app.core.security.context import SecurityContext
from app.core.security.passwords import (
    assert_password_strength,
    hash_password,
    is_forbidden_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert hashed != "CorrectHorseBatteryStaple!"
    assert verify_password("CorrectHorseBatteryStaple!", hashed)
    assert not verify_password("wrong", hashed)


def test_password_strength_rejects_seed_and_short_values() -> None:
    assert is_forbidden_password("123456")
    with pytest.raises(ValueError):
        assert_password_strength("123456")
    with pytest.raises(ValueError):
        hash_password("short")
    assert assert_password_strength("agency") == "agency"
    assert assert_password_strength("Staff1") == "Staff1"


def test_security_context_permission_and_tenant() -> None:
    tenant = uuid4()
    other = uuid4()
    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=tenant,
        session_id=uuid4(),
        email="a@example.com",
        role_id=uuid4(),
        role_code="test",
        permissions={"customer:read"},
    )
    ctx.require_permission("customer:read")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("customer:delete")
    ctx.assert_same_tenant(tenant)
    with pytest.raises(TenantAccessError):
        ctx.assert_same_tenant(other)


def test_suspended_tenant_blocked() -> None:
    ctx = SecurityContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        email="a@example.com",
        role_id=uuid4(),
        role_code="test",
        tenant_status="SUSPENDED",
    )
    with pytest.raises(TenantSuspendedError):
        ctx.require_active_tenant()
