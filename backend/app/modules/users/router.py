"""Staff user administration routes."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_current_context, get_db, require_permissions
from app.core.exceptions import AuthorizationError, ResourceNotFoundError
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.files.avatars import read_avatar
from app.modules.users.models import User
from app.modules.users.schemas import (
    UserCreateRequest,
    UserPublic,
    UserStatusRequest,
    UserUpdateRequest,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/options")
async def user_options(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext, Depends(require_permissions("user:create", "user:update"))
    ],
) -> dict:
    service = UserService(db, ctx)
    return success_response(
        await service.options(),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("")
async def list_users(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[
        SecurityContext,
        Depends(require_permissions("user:read", "user:create", "user:update", "user:disable")),
    ],
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    q: Annotated[str | None, Query(max_length=128)] = None,
) -> dict:
    service = UserService(db, ctx)
    items, total = await service.list_public(page=page, limit=limit, query=q)
    return success_response(
        {
            "items": [UserPublic.model_validate(item).model_dump(mode="json") for item in items],
            "page": page,
            "limit": limit,
            "total": total,
        },
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("")
async def create_user(
    body: UserCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("user:create"))],
) -> dict:
    service = UserService(db, ctx)
    item = await service.create(body)
    await db.commit()
    return success_response(
        UserPublic.model_validate(item).model_dump(mode="json"),
        message="User created",
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> Response:
    """Stream a staff avatar for same-tenant colleagues (cookie auth for <img>)."""
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise ResourceNotFoundError("Avatar not found")
    if not ctx.is_platform_admin and user.tenant_id != ctx.tenant_id:
        raise AuthorizationError("Avatar is not available")
    loaded = await asyncio.to_thread(
        read_avatar,
        tenant_id=user.tenant_id,
        subject_type="user",
        subject_id=user.id,
    )
    if loaded is None:
        raise ResourceNotFoundError("Avatar not found")
    body, content_type = loaded
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    body: UserUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("user:update"))],
) -> dict:
    service = UserService(db, ctx)
    item = await service.update(user_id, body)
    await db.commit()
    return success_response(
        UserPublic.model_validate(item).model_dump(mode="json"),
        message="User updated",
        request_id=getattr(request.state, "request_id", None),
    )


@router.patch("/{user_id}/status")
async def set_user_status(
    user_id: UUID,
    body: UserStatusRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(require_permissions("user:disable"))],
) -> dict:
    service = UserService(db, ctx)
    item = await service.set_status(user_id, body.status)
    await db.commit()
    return success_response(
        UserPublic.model_validate(item).model_dump(mode="json"),
        message="User updated",
        request_id=getattr(request.state, "request_id", None),
    )
