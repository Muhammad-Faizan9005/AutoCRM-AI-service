from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.core import readiness
from app.core.logging import configure_logging
from app.core.scheduler import scheduler
from app.core.jobs import register_jobs
from app.core.startup_checks import (
    verify_backend_connectivity,
    verify_provider_config,
    verify_security_config,
)
from app.db.pool import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    await init_pool()
    readiness.mark_database_connected()

    # Issue #5 — fail-fast if webhook token is missing outside dev
    try:
        await verify_security_config()
    except Exception as exc:
        logger.error("security_config_check_failed: %s", exc)
        await close_pool()
        raise

    # Fail-fast if credentials for an enabled provider/feature are missing.
    # Warns (not raises) in dev; aborts in prod. Previously these were checked
    # lazily mid-request inside the services.
    try:
        verify_provider_config()
    except Exception as exc:
        logger.error("provider_config_check_failed: %s", exc)
        await close_pool()
        raise

    backend_connected = False
    try:
        await verify_backend_connectivity()
        backend_connected = True
    except Exception as exc:
        readiness.mark_not_ready("backend_connectivity_failed", {"error": str(exc)})
        logger.exception("ai_service_startup_failed")
        if settings.ai_backend_connectivity_required:
            await close_pool()
            raise
    if settings.scheduler_enabled and backend_connected:
        register_jobs(scheduler)
        scheduler.start()
        readiness.mark_scheduler_started()
        logger.info("scheduler_starting")
    elif backend_connected:
        readiness.mark_ready("ready_scheduler_disabled")
    yield
    if settings.scheduler_enabled:
        scheduler.shutdown()
    await close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
