"""Process-local token bucket. Cheap, lock-free enough for one API process.

Cross-process caps (several Cloud Run instances) belong on the ESP
(SendGrid/SES) or a Redis limiter later — not in the request path.
"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    __slots__ = ("_rate", "_burst", "_tokens", "_updated", "_lock")

    def __init__(self, *, rate_per_second: float, burst: int | None = None) -> None:
        self._rate = max(float(rate_per_second), 0.05)
        self._burst = float(burst if burst is not None else max(1, int(self._rate * 2)))
        self._tokens = self._burst
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._updated = now
                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(min(wait, 2.0))
