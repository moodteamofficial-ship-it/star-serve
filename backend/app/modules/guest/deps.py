"""Guest-plane FastAPI dependencies.

A guest cookie never authenticates as staff. Staff JWTs are ignored here.
"""

from typing import Annotated, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.core.exceptions import AuthenticationError
from app.core.security.guest_capabilities import GuestCapability, GuestContext


def require_guest(*capabilities: GuestCapability) -> Callable[..., GuestContext]:
    async def _dependency(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> GuestContext:
        from app.modules.insurance.guest_session import load_guest_context

        guest = await load_guest_context(request, db)
        if guest is None:
            raise AuthenticationError("Start a guest quote session from the welcome screen")
        guest.require(*capabilities)
        guest.require_active_tenant()
        return guest

    return _dependency
