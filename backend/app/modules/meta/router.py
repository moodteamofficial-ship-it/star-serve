"""Runtime metadata — environment labels only, never secrets or DSNs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.core.dependencies.auth import get_current_context
from app.core.responses import success_response
from app.core.security.context import SecurityContext

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.get("/runtime")
async def runtime_meta(
    request: Request,
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
) -> dict:
    """Authenticated environment fingerprint for the staff env switcher.

    Unauthenticated callers used to learn the database provider, schema, and
    whether Supabase REST keys were configured. That is enough to aim a scan;
    signed-in staff still only get labels, never credentials.
    """
    _ = ctx
    settings = get_settings()
    return success_response(
        {
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "data_plane": settings.data_plane,
        },
        request_id=getattr(request.state, "request_id", None),
    )
