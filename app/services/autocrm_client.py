from __future__ import annotations

from uuid import UUID

import httpx

from app.config import settings
from app.core.security import AutoCRMAuth
from app.schemas.actions import AgentAction


class AutoCRMClient:
    def __init__(self) -> None:
        self.auth = AutoCRMAuth()

    async def dispatch_action(self, action: AgentAction) -> None:
        await self.create_action(action)

    async def create_action(self, action: AgentAction) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/actions",
                json=action.model_dump(mode="json"),
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def create_run(
        self,
        *,
        external_run_id: UUID,
        trigger_type: str,
        entity_id: UUID,
        entity_type: str,
        event_payload: dict[str, object],
    ) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        payload = {
            "external_run_id": str(external_run_id),
            "trigger_type": trigger_type,
            "entity_id": str(entity_id),
            "entity_type": entity_type,
            "status": "running",
            "event_payload": event_payload,
        }
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(f"{settings.autocrm_base_url}/api/agent/runs", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def get_run(self, run_id: UUID | str) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.get(f"{settings.autocrm_base_url}/api/agent/runs/{run_id}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def complete_run(
        self,
        run_id: UUID | str,
        *,
        status: str,
        summary: str | None = None,
        failure_cause: str | None = None,
        failure_detail: str | None = None,
    ) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        payload = {
            "status": status,
            "summary": summary,
            "failure_cause": failure_cause,
            "failure_detail": failure_detail,
        }
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.patch(f"{settings.autocrm_base_url}/api/agent/runs/{run_id}", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def create_run_trace(
        self,
        run_id: UUID | str,
        *,
        step: str,
        status: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        body = {"step": step, "status": status, "payload": payload}
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(f"{settings.autocrm_base_url}/api/agent/runs/{run_id}/trace", json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def list_run_traces(self, run_id: UUID | str) -> list[dict[str, object]]:
        return await self._get_list(f"/api/agent/runs/{run_id}/trace")

    async def get_entity_memory(self, entity_type: str, entity_id: UUID) -> list[dict[str, object]]:
        return await self._get_list(f"/api/agent/memory/{entity_type}/{entity_id}")

    async def get_entity_snapshot(self, entity_type: str, entity_id: UUID) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.get(
                f"{settings.autocrm_base_url}/api/agent/entity-snapshot/{entity_type}/{entity_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def get_rag_snapshot(
        self,
        *,
        changed_since: str | None = None,
        entity_type: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        params: dict[str, object] = {}
        if changed_since:
            params["changed_since"] = changed_since
        if entity_type:
            params["entity_type"] = entity_type
        if limit:
            params["limit"] = limit
        async with httpx.AsyncClient(timeout=max(settings.autocrm_auth_timeout, 30), follow_redirects=True) as client:
            response = await client.get(
                f"{settings.autocrm_base_url}/api/agent/rag/snapshot",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def reconcile_rag_sources(self, sources: list[dict[str, str]]) -> dict[str, object]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=max(settings.autocrm_auth_timeout, 30), follow_redirects=True) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/rag/reconcile",
                json={"sources": sources},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

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

    async def sweep_lead_scores(self, limit: int = 100) -> dict[str, object]:
        """Ask AutoCRM backend to recalculate a batch of lead scores."""
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.post(
                f"{settings.autocrm_base_url}/api/agent/leads/score/sweep",
                params={"limit": limit},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def _get_list(self, path: str) -> list[dict[str, object]]:
        headers = await self.auth.get_async_headers()
        async with httpx.AsyncClient(timeout=settings.autocrm_auth_timeout, follow_redirects=True) as client:
            response = await client.get(f"{settings.autocrm_base_url}{path}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
