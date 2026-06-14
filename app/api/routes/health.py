from __future__ import annotations

from fastapi import APIRouter

from app.config import settings


router = APIRouter()


@router.get("")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config")
async def config_health() -> dict[str, object]:
    llm_configured = bool(settings.llm_enabled and settings.llm_provider and settings.ollama_base_url)
    return {
        "status": "ok",
        "assemblyai": "configured" if settings.assemblyai_api_key else "missing",
        "llm": "configured" if llm_configured else "missing_or_disabled",
        "backend_url": "configured" if settings.autocrm_base_url else "missing",
        "recordings_dir": "configured" if settings.transcription_recordings_dir else "auto_detect",
    }
