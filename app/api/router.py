from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.events import router as events_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import router as runs_router


api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(events_router, prefix="/agent", tags=["agent-events"])
api_router.include_router(runs_router, prefix="/agent", tags=["agent-runs"])
