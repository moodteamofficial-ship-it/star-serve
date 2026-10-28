"""Guest claim HTTP surface — isolated from staff claim actions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.core.responses import success_response
from app.core.security.guest_capabilities import GuestCapability, GuestContext
from app.modules.claims.guest_schemas import (
    GuestClaimCreateRequest,
    GuestClaimFollowupRequest,
    GuestClaimLookupRequest,
)
from app.modules.claims.guest_service import GuestClaimService
from app.modules.guest.deps import require_guest
from app.modules.insurance.guest_session import (
    enforce_guest_claim_followup_limit,
    enforce_guest_claim_limit,
    enforce_guest_identity_lookup_limit,
    release_guest_claim_slot,
    reserve_guest_claim_slot,
)
from app.modules.system_config.deps import require_system_service

router = APIRouter(prefix="/insurance/guest/claims", tags=["Guest Claims"])


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("")
async def file_guest_claim(
    body: GuestClaimCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext,
        Depends(require_guest(GuestCapability.FILE_CLAIM)),
    ],
    _: Annotated[None, Depends(require_system_service("claims"))],
) -> dict:
    await enforce_guest_claim_limit(request)
    await reserve_guest_claim_slot(request)
    service = GuestClaimService(db, guest, request)
    try:
        data = await service.file(body)
        await db.commit()
    except Exception:
        await release_guest_claim_slot(request)
        raise
    return success_response(data, message="Claim received", request_id=_rid(request))


@router.post("/lookup")
async def lookup_guest_claim(
    body: GuestClaimLookupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext,
        Depends(
            require_guest(GuestCapability.VIEW_OWN_CLAIM, GuestCapability.FOLLOW_UP_CLAIM)
        ),
    ],
) -> dict:
    await enforce_guest_identity_lookup_limit(request)
    service = GuestClaimService(db, guest, request)
    data = await service.lookup(body)
    await db.commit()
    return success_response(data, message="Claim located", request_id=_rid(request))


@router.get("/{claim_id}")
async def get_guest_claim(
    claim_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext,
        Depends(require_guest(GuestCapability.VIEW_OWN_CLAIM)),
    ],
) -> dict:
    service = GuestClaimService(db, guest, request)
    data = await service.get(claim_id)
    return success_response(data, request_id=_rid(request))


@router.post("/{claim_id}/follow-up")
async def follow_up_guest_claim(
    claim_id: UUID,
    body: GuestClaimFollowupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    guest: Annotated[
        GuestContext,
        Depends(require_guest(GuestCapability.FOLLOW_UP_CLAIM)),
    ],
    _: Annotated[None, Depends(require_system_service("claims"))],
) -> dict:
    await enforce_guest_claim_followup_limit(request)
    service = GuestClaimService(db, guest, request)
    data = await service.follow_up(claim_id, body.message)
    await db.commit()
    return success_response(data, message="Follow-up sent", request_id=_rid(request))
