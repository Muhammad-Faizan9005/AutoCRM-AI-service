from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_webhook_token
from app.config import settings
from app.core.readiness import snapshot


router = APIRouter()


@router.get("")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check() -> dict[str, object]:
    state = snapshot()
    if not state["ready"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=state)
    return {"status": "ready", **state}


@router.get("/config", dependencies=[Depends(require_webhook_token)])
async def config_health() -> dict[str, object]:
    llm_configured = bool(settings.llm_enabled and settings.llm_provider and settings.ollama_base_url)
    return {
        "status": "ok",
        "assemblyai": "configured" if settings.assemblyai_api_key else "missing",
        "llm": "configured" if llm_configured else "missing_or_disabled",
        "backend_url": "configured" if settings.autocrm_base_url else "missing",
        "recordings_dir": "configured" if settings.transcription_recordings_dir else "auto_detect",
    }
