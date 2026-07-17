from __future__ import annotations

from app.config import settings


class AutoCRMAuth:
    """
    Handles authentication for AI service -> AutoCRM backend calls.

    The service token authenticates this AI service process. X-AI-Agent-Key is
    optional runtime attribution for logs/visibility, not the token owner.
    """

    def _build_headers(self) -> dict[str, str]:
        if not settings.autocrm_ai_service_token:
            raise RuntimeError(
                "AI service backend auth is not configured. Set AUTOCRM_AI_SERVICE_TOKEN "
                "in AI_service/Autocrm_AI_system/.env."
            )
        headers = {"X-AI-Service-Token": settings.autocrm_ai_service_token}
        if settings.autocrm_ai_agent_key:
            headers["X-AI-Agent-Key"] = settings.autocrm_ai_agent_key
        return headers

    def get_auth_headers(self) -> dict[str, str]:
        """Return auth headers for requests."""
        return self._build_headers()

    async def get_async_headers(self) -> dict[str, str]:
        """Return auth headers for requests (async call sites)."""
        return self._build_headers()
