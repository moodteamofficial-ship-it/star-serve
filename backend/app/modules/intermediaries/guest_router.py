"""Public agent self-registration — isolated from staff intermediary routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.core.responses import success_response
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.modules.guest.deps import require_guest
from app.modules.insurance.guest_session import enforce_guest_agent_apply_limit
from app.modules.intermediaries.guest_service import GuestAgentApplicationService
from app.modules.intermediaries.schemas import GuestAgentApplicationRequest

router = APIRouter(prefix="/insurance/guest/agents", tags=["Guest Agent Applications"])


@router.post("/apply")
async def apply_as_agent(
    body: GuestAgentApplicationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[GuestContext, Depends(require_guest(GuestCapability.APPLY_AS_AGENT))],
) -> dict:
    await enforce_guest_agent_apply_limit(request)
    data = await GuestAgentApplicationService(db, guest, request).apply(body)
    await db.commit()
    return success_response(
        data,
        message="Application received. An admin will review it shortly.",
        request_id=getattr(request.state, "request_id", None),
    )
