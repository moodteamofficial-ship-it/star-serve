"""Overview / home dashboard routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_current_context, get_db
from app.core.responses import success_response
from app.core.security.context import SecurityContext
from app.modules.overview.service import OverviewService

router = APIRouter(prefix="/overview", tags=["Overview"])


@router.get("/summary")
async def overview_summary(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[SecurityContext, Depends(get_current_context)],
    period: Annotated[Literal["7d", "30d", "90d", "ytd"], Query()] = "30d",
) -> dict:
    """Permission-gated tenant aggregates for the home overview.

    Each section is omitted when the caller lacks the matching read permission.
    Totals come from a single RLS-scoped SQL round-trip (short-lived cache).
    """
    data = await OverviewService(db, ctx).summary(period=period)
    return success_response(
        data,
        request_id=getattr(request.state, "request_id", None),
    )
