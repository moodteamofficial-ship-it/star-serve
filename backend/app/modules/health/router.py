"""Liveness and readiness probes — no sensitive diagnostics."""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.redis_client import get_redis_client, set_redis_client
from app.core.dependencies.auth import get_db
from app.core.responses import success_response

router = APIRouter(tags=["Health"])


def set_redis(client: Redis | None) -> None:
    set_redis_client(client)


@router.get("/health")
async def health() -> dict:
    return success_response({"status": "ok"}, message="Alive")


@router.get("/ready")
async def ready(db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    await db.execute(text("SELECT 1"))
    redis = get_redis_client()
    redis_ok = True
    if redis is not None:
        try:
            await redis.ping()
        except Exception:
            redis_ok = False
    if not redis_ok:
        from fastapi.responses import JSONResponse

        from app.core.responses import error_response

        return JSONResponse(  # type: ignore[return-value]
            status_code=503,
            content=error_response(
                code="NOT_READY",
                message="One or more dependencies are unavailable",
            ),
        )
    return success_response({"database": "ok", "redis": "ok" if redis else "skipped"})
