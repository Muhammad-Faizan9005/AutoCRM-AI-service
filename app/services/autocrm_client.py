from __future__ import annotations

import httpx

from app.config import settings
from app.core.security import AutoCRMAuth
from app.schemas.actions import AgentAction


class AutoCRMClient:
    def __init__(self) -> None:
        self.auth = AutoCRMAuth()

    async def dispatch_action(self, action: AgentAction) -> None:
        token = await self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/actions",
                json=action.model_dump(),
                headers=headers,
            )
            response.raise_for_status()

    async def list_leads(self) -> list[dict[str, object]]:
        return await self._get_list("/api/leads")

    async def list_deals(self) -> list[dict[str, object]]:
        return await self._get_list("/api/deals")

    async def list_users(self) -> list[dict[str, object]]:
        return await self._get_list("/api/users")

    async def _get_list(self, path: str) -> list[dict[str, object]]:
        token = await self.auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout) as client:
            response = await client.get(f"{settings.autocrm_base_url}{path}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
