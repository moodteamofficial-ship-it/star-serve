"""Standalone email worker for high-volume drains.

Run this instead of (or as well as) the in-process FastAPI dispatcher when
outbound volume is large. Postgres SKIP LOCKED keeps workers from double-sending.

    python -m app.modules.notifications.worker
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.integrations.notifications.factory import shutdown_notification_providers
from app.modules.notifications.dispatcher import start_email_dispatcher, stop_email_dispatcher

logger = get_logger(__name__)


async def _main() -> None:
    settings = get_settings()
    configure_logging()
    logger.info(
        "email_worker_boot",
        extra={"provider": settings.resolved_email_provider},
    )
    dispatcher = await start_email_dispatcher(settings)
    if dispatcher is None:
        raise SystemExit(
            "Email dispatcher is disabled (stub provider or EMAIL_WORKER_ENABLED=false)"
        )
    idle = asyncio.Event()
    try:
        await idle.wait()
    except asyncio.CancelledError:
        raise
    finally:
        await stop_email_dispatcher()
        await shutdown_notification_providers()


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
