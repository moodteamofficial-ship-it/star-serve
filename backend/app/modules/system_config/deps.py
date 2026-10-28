"""FastAPI dependency helpers for system service toggles."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies.auth import get_db
from app.modules.system_config.service import SystemConfigService


def require_system_service(service: str) -> Callable:
    async def _dependency(db: Annotated[AsyncSession, Depends(get_db)]) -> None:
        await SystemConfigService(db).require_service(service)

    return _dependency
