"""Phase 8 — dangerous capabilities are closed allowlists, not env accidents."""

from __future__ import annotations

import inspect
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, ValidationAppError
from app.core.security.context import SecurityContext
from app.core.security.media_url import sanitize_avatar_url
from app.core.security.permissions import effective_permissions
from app.main import _assert_production_secrets
from app.modules.customers.service import CustomerService
from app.modules.roles import router as roles_router


def _ctx(**overrides) -> SecurityContext:
    values = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "session_id": uuid4(),
        "email": "a@agency.local",
        "role_id": uuid4(),
        "role_code": "agency_admin",
        "permissions": {"*:*", "customer:read"},
    }
    values.update(overrides)
    return SecurityContext(**values)


def test_agency_wildcard_is_stripped_and_ignored() -> None:
    perms = effective_permissions(
        is_platform_admin=False,
        permissions={"*:*", "customer:read"},
    )
    assert perms == {"customer:read"}
    ctx = _ctx(is_platform_admin=False, permissions={"*:*"})
    with pytest.raises(AuthorizationError):
        ctx.require_permission("customer:delete")
    with pytest.raises(AuthorizationError):
        ctx.require_permission("platform:tenant:manage")
    assert ctx.can_manage_users() is False


def test_platform_admin_keeps_wildcard() -> None:
    perms = effective_permissions(is_platform_admin=True, permissions={"*:*"})
    assert "*:*" in perms
    ctx = _ctx(is_platform_admin=True, permissions={"*:*"})
    ctx.require_permission("customer:delete")
    ctx.require_permission("platform:config:manage")


def test_role_replace_rejects_wildcard_for_agency_roles() -> None:
    source = inspect.getsource(roles_router.replace_role_permissions)
    assert "PLATFORM_WILDCARD" in source
    assert "platform_admin" in source


def test_customer_assign_validates_tenant_user() -> None:
    source = inspect.getsource(CustomerService.assign)
    assert "require_assignable_tenant_user" in source


def test_avatar_url_rejects_dangerous_schemes_and_hosts() -> None:
    assert sanitize_avatar_url(None) is None
    assert (
        sanitize_avatar_url("https://cdn.example.com/a.png") == "https://cdn.example.com/a.png"
    )
    same_origin = (
        "/api/v1/users/65dcb61c-05ef-488a-8ad7-b992bfdcc9df/avatar?v=1856bc913f0a9094"
    )
    assert sanitize_avatar_url(same_origin) == same_origin
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("javascript:alert(1)")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("https://localhost/a.png")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("https://192.168.1.4/a.png")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("https://evil.example/a.png", allowed_hosts="cdn.example.com")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("/api/v1/users/not-a-uuid/avatar")
    with pytest.raises(ValidationAppError):
        sanitize_avatar_url("/etc/passwd")


def test_production_ignores_remote_insecure_overrides() -> None:
    remote = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
        allow_insecure_production=True,
        allow_receipt_confirm=True,
        allow_manual_wallet_credit=True,
    )
    assert remote.database_host_is_local is False
    assert remote.local_insecure_override is False
    assert remote.receipt_confirm_allowed is False
    assert remote.manual_wallet_credit_allowed is False
    with pytest.raises(RuntimeError, match="ALLOW_INSECURE_PRODUCTION"):
        _assert_production_secrets(remote)


def test_production_receipt_flag_alone_is_refused() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://u:p@db.internal:5432/starserve",
        csrf_secret="y" * 32,
        encryption_key="z" * 32,
        jwt_algorithm="RS256",
        allow_receipt_confirm=True,
        guest_quote_enabled=False,
    )
    assert settings.receipt_confirm_allowed is False
    with pytest.raises(RuntimeError, match="ALLOW_RECEIPT_CONFIRM"):
        _assert_production_secrets(settings)


def test_local_dual_plane_can_still_enable_receipt_confirm() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+asyncpg://starserve:starserve@localhost:5432/starserve",
        allow_insecure_production=True,
        allow_receipt_confirm=True,
    )
    assert settings.local_insecure_override is True
    assert settings.receipt_confirm_allowed is True
    _assert_production_secrets(settings)


def test_cookie_samesite_none_requires_secure() -> None:
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=none"):
        Settings(cookie_samesite="none", cookie_secure=False, app_env="staging")
    settings = Settings(cookie_samesite="none", cookie_secure=True, app_env="staging")
    assert settings.cookie_samesite == "none"
    assert settings.cookie_secure is True


def test_staging_skips_production_secret_guards() -> None:
    settings = Settings(
        app_env="staging",
        csrf_secret="change-me-csrf-dev-only",
        encryption_key="change-me-32-byte-encryption-key!!",
        guest_quote_enabled=True,
        guest_signing_secret="",
    )
    _assert_production_secrets(settings)
