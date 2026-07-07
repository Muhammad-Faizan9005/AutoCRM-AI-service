from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from app.config import settings


class AutoCRMAuth:
    """
    Handles authentication for AI service -> AutoCRM backend calls.

    The service token authenticates this AI service process. X-AI-Agent-Key is
    optional runtime attribution for logs/visibility, not the token owner.
    """

    def __init__(self) -> None:
        # Legacy JWT fields
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def _uses_service_token(self) -> bool:
        """Return True when the new AI service credentials are configured."""
        return bool(settings.autocrm_ai_service_token)

    def get_auth_headers(self) -> dict[str, str]:
        """
        Return synchronous auth headers for requests that do not need token refresh.
        Only works when using service-token auth.
        """
        if self._uses_service_token():
            headers = {"X-AI-Service-Token": settings.autocrm_ai_service_token}
            if settings.autocrm_ai_agent_key:
                headers["X-AI-Agent-Key"] = settings.autocrm_ai_agent_key
            return headers
        raise RuntimeError("Cannot build synchronous headers for legacy email/password auth; use await get_async_headers()")

    async def get_async_headers(self) -> dict[str, str]:
        """
        Return the correct auth headers for the current configuration.
        - New path:    X-AI-Service-Token, plus optional X-AI-Agent-Key
        - Legacy path: no longer supported after the backend moved human auth to
          httpOnly cookies. Configure service-token auth for AI worker calls.
        """
        if self._uses_service_token():
            headers = {"X-AI-Service-Token": settings.autocrm_ai_service_token}
            if settings.autocrm_ai_agent_key:
                headers["X-AI-Agent-Key"] = settings.autocrm_ai_agent_key
            return headers
        raise RuntimeError(
            "AI service backend auth is not configured. Set AUTOCRM_AI_SERVICE_TOKEN "
            "in AI_service/Autocrm_AI_system/.env. "
            "Legacy AUTOCRM_AUTH_EMAIL/AUTOCRM_AUTH_PASSWORD cannot be used after "
            "the backend moved human auth tokens into httpOnly cookies."
        )

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
            if not self._token:
                raise RuntimeError(
                    "Backend login did not return an access_token. Legacy AI "
                    "email/password auth is incompatible with cookie-based auth; "
                    "configure AUTOCRM_AI_AGENT_KEY and AUTOCRM_AI_SERVICE_TOKEN instead."
                )
            self._expires_at = datetime.utcnow() + timedelta(minutes=55)
            return self._token
