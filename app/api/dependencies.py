from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_webhook_token(
    token: str | None = Header(default=None, alias="X-AutoCRM-AI-Webhook-Token"),
) -> None:
    expected = settings.ai_service_webhook_token
    if not expected and settings.app_env.lower() in {"development", "dev", "test"}:
        return
    if not expected or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid AI service webhook token",
        )
