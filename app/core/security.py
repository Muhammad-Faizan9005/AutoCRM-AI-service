from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from app.config import settings


class AutoCRMAuth:
    """
    Handles authentication for AI service -> AutoCRM backend calls.

    Priority order:
    1. AI service token (X-AI-Agent-Key + X-AI-Service-Token headers) -- preferred
       Requires AUTOCRM_AI_AGENT_KEY and AUTOCRM_AI_SERVICE_TOKEN set in .env
    2. Legacy email/password JWT login -- fallback for backward compatibility
       Requires AUTOCRM_AUTH_EMAIL and AUTOCRM_AUTH_PASSWORD set in .env
    """

    def __init__(self) -> None:
        # Legacy JWT fields
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def _uses_service_token(self) -> bool:
        """Return True when the new AI service credentials are configured."""
        return bool(settings.autocrm_ai_agent_key and settings.autocrm_ai_service_token)

    def get_auth_headers(self) -> dict[str, str]:
        """
        Return synchronous auth headers for requests that do not need token refresh.
        Only works when using the new service-token auth.
        Raises RuntimeError for the legacy path (use get_token() / get_async_headers() instead).
        """
        if self._uses_service_token():
            return {
                "X-AI-Agent-Key": settings.autocrm_ai_agent_key,
                "X-AI-Service-Token": settings.autocrm_ai_service_token,
            }
        raise RuntimeError("Cannot build synchronous headers for legacy email/password auth; use await get_async_headers()")

    async def get_async_headers(self) -> dict[str, str]:
        """
        Return the correct auth headers for the current configuration.
        - New path:    X-AI-Agent-Key + X-AI-Service-Token (no network call needed)
        - Legacy path: Bearer <JWT>  (fetches/refreshes token via /api/auth/login)
        """
        if self._uses_service_token():
            return {
                "X-AI-Agent-Key": settings.autocrm_ai_agent_key,
                "X-AI-Service-Token": settings.autocrm_ai_service_token,
            }
        # Legacy: obtain/refresh JWT
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}

    async def get_token(self) -> str:
        """
        Legacy method: obtain a JWT via email/password login.
        Cached for 55 minutes to match the 1-hour token lifetime.
        """
        if self._token and self._expires_at and datetime.utcnow() < self._expires_at:
            return self._token

        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/auth/login",
                json={
                    "email": settings.autocrm_auth_email,
                    "password": settings.autocrm_auth_password,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._token = data.get("access_token") or ""
            self._expires_at = datetime.utcnow() + timedelta(minutes=55)
            return self._token
