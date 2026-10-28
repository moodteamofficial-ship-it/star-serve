"""JWT access tokens (asymmetric) and opaque refresh token helpers.

Access tokens carry identity claims (user, session, tenant, role id).
Permission checks always resolve live from the database on each request.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from jwt.exceptions import InvalidTokenError as JWTError
import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


def _load_key(path: str | None, inline: str | None) -> str:
    if inline:
        return inline.replace("\\n", "\n")
    if not path:
        raise AuthenticationError("JWT signing keys are not configured")
    key_path = Path(path)
    if not key_path.exists():
        raise AuthenticationError("JWT signing keys are not configured")
    return key_path.read_text(encoding="utf-8")


def get_private_key() -> str:
    settings = get_settings()
    return _load_key(settings.jwt_private_key_path, settings.jwt_private_key)


def get_public_key() -> str:
    settings = get_settings()
    return _load_key(settings.jwt_public_key_path, settings.jwt_public_key)


def create_access_token(
    *,
    user_id: str,
    session_id: str,
    tenant_id: str,
    role_id: str,
    role_code: str,
    email: str,
    is_platform_admin: bool,
    tenant_status: str,
    branch_ids: Sequence[str] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    # Identity only — never embed permissions; authz is live from role_permissions.
    payload: dict[str, Any] = {
        "sub": user_id,
        "sid": session_id,
        "tid": tenant_id,
        "rid": role_id,
        "rc": role_code,
        "email": email,
        "ipa": bool(is_platform_admin),
        "ts": tenant_status,
        "bids": list(branch_ids or []),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_minutes)).timestamp()),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, get_private_key(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, *, verify_exp: bool = True) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            get_public_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["exp", "sub", "iss", "aud"],
                "verify_exp": verify_exp,
            },
        )
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    if payload.get("typ") != "access":
        raise AuthenticationError("Invalid access token type")
    return payload


def generate_refresh_token() -> str:
    return uuid4().hex + uuid4().hex
