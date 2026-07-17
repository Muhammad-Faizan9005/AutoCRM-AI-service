from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.metrics import get_metrics_snapshot

router = APIRouter()


@router.get("/metrics", tags=["observability"])
async def metrics() -> JSONResponse:
    """Expose operational metrics as JSON."""
    return JSONResponse(content=get_metrics_snapshot())
