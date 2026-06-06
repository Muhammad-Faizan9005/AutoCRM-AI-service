from __future__ import annotations

import httpx

from app.config import settings
from app.core.security import AutoCRMAuth
from app.schemas.actions import AgentAction


class AutoCRMClient:
    def __init__(self) -> None:
        self.auth = AutoCRMAuth()

    async def dispatch_action(self, action: AgentAction) -> None:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/actions",
                json=action.model_dump(mode="json"),
                headers=headers,
            )
            response.raise_for_status()

    async def list_leads(self) -> list[dict[str, object]]:
        return await self._get_list("/api/leads/")

    async def list_deals(self) -> list[dict[str, object]]:
        return await self._get_list("/api/deals/")

    async def list_users(self) -> list[dict[str, object]]:
        return await self._get_list("/api/users")

    async def list_agent_settings(self) -> list[dict[str, object]]:
        return await self._get_list("/api/agent/settings")

    async def list_ai_agents(self) -> list[dict[str, object]]:
        """Return the registered AI agent registry from the backend."""
        return await self._get_list("/api/agent/ai-agents")

    async def heartbeat(self) -> dict[str, object]:
        """Ping the AI service heartbeat endpoint to update last_seen_at."""
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/ai-service/heartbeat",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def _get_list(self, path: str) -> list[dict[str, object]]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.get(f"{settings.autocrm_base_url}{path}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
