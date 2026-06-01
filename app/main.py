from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.core.logging import configure_logging
from app.core.scheduler import scheduler
from app.core.jobs import register_jobs
from app.db.pool import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    await init_pool()
    if settings.scheduler_enabled:
        register_jobs(scheduler)
        scheduler.start()
    yield
    if settings.scheduler_enabled:
        scheduler.shutdown()
    await close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)
