"""Auth HTTP routes — thin controllers."""

import asyncio
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies.auth import get_current_context, get_db
from app.core.exceptions import AuthenticationError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.core.security.request import client_ip as request_client_ip
from app.modules.auth.schemas import (
    LoginData,
    LoginRequest,
    PasswordChangeRequest,
    PreferredAppEnvRequest,
    UserPublic,
)
from app.modules.auth.service import AuthService
from app.modules.files.avatars import public_user_avatar_url, store_avatar
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _new_csrf_token() -> str:
    """Independent CSRF double-submit token — never derived from the refresh token."""
    return secrets.token_urlsafe(32)


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def _cookie_common() -> dict:
    settings = get_settings()
    return {
        "secure": settings.cookie_secure or settings.is_production,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain or None,
        "path": "/",
    }


def _set_auth_cookies(response: Response, *, access: str, refresh: str, csrf: str) -> None:
    settings = get_settings()
    common = {**_cookie_common(), "httponly": True}
    response.set_cookie(
        settings.access_cookie_name,
        access,
        max_age=settings.jwt_access_token_minutes * 60,
        **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh,
        max_age=settings.jwt_refresh_token_days * 86400,
        **common,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=settings.jwt_refresh_token_days * 86400,
        httponly=False,
        secure=common["secure"],
        samesite=common["samesite"],
        domain=common["domain"],
        path=common["path"],
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    common = _cookie_common()
    for name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
        settings.guest_cookie_name,
    ):
        response.delete_cookie(
            name,
            path=common["path"],
            domain=common["domain"],
            secure=common["secure"],
            samesite=common["samesite"],
        )


def _user_public(user: User, *, permissions: list[str], role_code: str) -> UserPublic:
    settings = get_settings()
    if user.role_id is None:
        raise RuntimeError("User missing role_id")
    return UserPublic(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        phone=_mask_phone(user.phone),
        tenant_id=str(user.tenant_id),
        role_id=str(user.role_id),
        role_code=role_code,
        branch_id=str(user.branch_id) if user.branch_id else None,
        country_code=user.country_code,
        phone_country_code=user.phone_country_code,
        country_id=str(user.country_id) if user.country_id else None,
        currency=user.currency or "KES",
        timezone=user.timezone,
        locale=user.locale,
        avatar_url=user.avatar_url,
        permissions=permissions,
        app_env=settings.app_env,
        preferred_app_env=user.preferred_app_env or settings.app_env,
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ip_address = request_client_ip(request)
    client_device_id = (request.headers.get("x-client-device-id") or "").strip() or None

    service = AuthService(db)
    user, _tenant, access, refresh, _session, resolved = await service.authenticate(
        email=body.email,
        password=body.password,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
        client_device_id=client_device_id,
    )
    _set_auth_cookies(response, access=access, refresh=refresh, csrf=_new_csrf_token())
    await db.commit()
    data = LoginData(
        user=_user_public(
            user,
            permissions=sorted(resolved.permissions),
            role_code=resolved.code,
        ),
        expires_in=get_settings().jwt_access_token_minutes * 60,
    )
    return success_response(
        data.model_dump(),
        message="Login successful",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    settings = get_settings()
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise AuthenticationError("Missing refresh token")
    service = AuthService(db)
    user, access, new_refresh, _session, resolved = await service.refresh(
        refresh_token=token,
        ip_address=request_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, access=access, refresh=new_refresh, csrf=_new_csrf_token())
    await db.commit()
    data = LoginData(
        user=_user_public(
            user,
            permissions=sorted(resolved.permissions),
            role_code=resolved.code,
        ),
        expires_in=settings.jwt_access_token_minutes * 60,
    )
    return success_response(
        data.model_dump(),
        message="Session refreshed",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


def _request_access_token(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name)
    if token:
        return token
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    settings = get_settings()
    service = AuthService(db)
    await service.logout(
        refresh_token=request.cookies.get(settings.refresh_cookie_name),
        access_token=_request_access_token(request),
    )
    _clear_auth_cookies(response)
    await db.commit()
    return success_response(
        message="Logged out",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.get("/me")
async def me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> dict:
    user = await db.get(User, ctx.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthenticationError("Session is no longer valid")
    data = _user_public(
        user,
        permissions=sorted(ctx.permissions),
        role_code=ctx.role_code,
    )
    return success_response(
        data.model_dump(),
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/me/avatar")
async def upload_my_avatar(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Upload the signed-in user's profile photo (required for the staff shell)."""
    user = await db.get(User, ctx.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthenticationError("Session is no longer valid")
    payload = await file.read()
    stored = await asyncio.to_thread(
        store_avatar,
        tenant_id=user.tenant_id,
        subject_type="user",
        subject_id=user.id,
        payload=payload,
    )
    user.avatar_url = public_user_avatar_url(user.id, version=stored.sha256)
    await db.commit()
    await db.refresh(user)
    data = _user_public(
        user,
        permissions=sorted(ctx.permissions),
        role_code=ctx.role_code,
    )
    return success_response(
        data.model_dump(),
        message="Profile photo saved",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.patch("/preferred-env")
async def set_preferred_env(
    body: PreferredAppEnvRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> dict:
    user = await db.get(User, ctx.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthenticationError("Session is no longer valid")
    service = AuthService(db)
    user = await service.set_preferred_app_env(user=user, app_env=body.app_env)
    await db.commit()
    data = _user_public(
        user,
        permissions=sorted(ctx.permissions),
        role_code=ctx.role_code,
    )
    return success_response(
        data.model_dump(),
        message="Preferred environment updated",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> dict:
    user = await db.get(User, ctx.user_id)
    if user is None:
        raise AuthenticationError("Session is no longer valid")
    service = AuthService(db)
    await service.change_password(
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    _clear_auth_cookies(response)
    await db.commit()
    return success_response(
        message="Password changed. Please sign in again.",
        request_id=getattr(request.state, "request_id", None),
        job_id=getattr(request.state, "job_id", None),
    )
