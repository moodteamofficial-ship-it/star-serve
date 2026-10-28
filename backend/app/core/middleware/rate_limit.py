"""Fixed-window rate limiting — Redis when available, else per-instance memory.

Cloud Run ships without Memorystore by default. Login brute-force defense still
uses DB lockout; this middleware only caps request volume.
"""

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.database.redis_client import get_redis_client
from app.core.logging.context import get_job_id, get_request_id
from app.core.responses import error_response
from app.core.security.request import client_ip

# Per-instance fallback when Redis is unset or unreachable (Cloud Run default).
_MEMORY_BUCKETS: dict[str, tuple[int, float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.redis = redis_client
        self.settings = get_settings()
        self.limit, self.window = self._parse_limit(self.settings.rate_limit_default)

    @staticmethod
    def _parse_limit(spec: str) -> tuple[int, int]:
        # e.g. "120/minute"
        try:
            count_s, period = spec.split("/")
            count = int(count_s)
            period = period.strip().lower()
            window = {"second": 1, "minute": 60, "hour": 3600}.get(period, 60)
            return count, window
        except Exception:
            return 120, 60

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        client = client_ip(request) or (request.client.host if request.client else "unknown")
        path_key = "auth" if "/auth/" in request.url.path else "api"
        # Stricter auth limits
        limit = 20 if path_key == "auth" else self.limit
        window = 60 if path_key == "auth" else self.window
        key = f"rl:{path_key}:{client}:{request.url.path}"

        allowed = await self._hit(key, limit, window)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=error_response(
                    code="RATE_LIMIT_EXCEEDED",
                    message="Too many requests. Please try again later.",
                    request_id=get_request_id(),
                    job_id=get_job_id(),
                ),
            )
        return await call_next(request)

    async def _hit(self, key: str, limit: int, window: int) -> bool:
        import time

        redis = self.redis if self.redis is not None else get_redis_client()
        if redis is not None:
            try:
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, window)
                return int(count) <= limit
            except Exception:
                pass

        now = time.time()
        count, reset = _MEMORY_BUCKETS.get(key, (0, now + window))
        if now > reset:
            count, reset = 0, now + window
        count += 1
        _MEMORY_BUCKETS[key] = (count, reset)
        return count <= limit
