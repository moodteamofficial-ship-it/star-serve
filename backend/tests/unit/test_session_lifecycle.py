"""Phase 4 — lockout and logout revoke the server session."""

from __future__ import annotations

import inspect

from app.core.database.enums import UserStatus
from app.core.dependencies import auth as auth_deps
from app.core.dependencies.auth import get_current_context
from app.core.security.tokens import decode_access_token
from app.modules.auth import router as auth_router
from app.modules.auth.service import AuthService
from app.modules.roles import router as roles_router


def test_lockout_revokes_active_sessions() -> None:
    source = inspect.getsource(AuthService.authenticate)
    assert "UserStatus.LOCKED.value" in source
    assert "revoke_all_sessions" in source


def test_access_and_refresh_reject_locked_users() -> None:
    access = inspect.getsource(get_current_context)
    refresh = inspect.getsource(AuthService.refresh)
    assert "UserStatus.LOCKED.value" in access
    assert "UserStatus.LOCKED.value" in refresh
    assert "revoke_all_sessions" in refresh
    assert UserStatus.LOCKED.value == "LOCKED"


def test_logout_revokes_from_access_token_when_refresh_missing() -> None:
    route = inspect.getsource(auth_router.logout)
    service = inspect.getsource(AuthService.logout)
    assert "access_token" in route
    assert "_request_access_token" in route
    assert "verify_exp=False" in service
    assert "refresh_token" in service
    assert "return" not in service.split("if refresh_token:", 1)[1].split("if access_token:", 1)[0]


def test_decode_access_token_can_skip_expiry() -> None:
    source = inspect.getsource(decode_access_token)
    assert "verify_exp" in source


def test_logout_clears_cookies_after_server_revoke() -> None:
    route = inspect.getsource(auth_router.logout)
    assert "_clear_auth_cookies" in route
    assert "service.logout" in route
    # Cookie delete is not sufficient by itself.
    assert route.index("service.logout") < route.index("_clear_auth_cookies")


def test_permission_updates_keep_sessions() -> None:
    source = inspect.getsource(roles_router.replace_role_permissions)
    assert "revoke_sessions_for_role" not in source
    assert "role.permissions_replace" in source


def test_disabling_a_role_revokes_other_sessions_not_self() -> None:
    source = inspect.getsource(roles_router.update_role)
    assert "revoke_sessions_for_role" in source
    assert "You cannot disable the role you are currently signed in with" in source


def test_me_stays_up_when_platform_is_switched_off() -> None:
    source = inspect.getsource(get_current_context)
    assert "_is_session_keepalive_path" in source
    assert auth_deps._is_session_keepalive_path("/api/v1/auth/me") is True
    assert auth_deps._is_session_keepalive_path("/api/v1/auth/preferred-env") is True
    assert auth_deps._is_session_keepalive_path("/api/v1/claims") is False
