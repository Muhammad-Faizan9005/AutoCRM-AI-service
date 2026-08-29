"""AI-service client for the backend's internal frontdesk contracts.

The AI service never writes to the database. Every CRM side effect goes
through these validated backend endpoints. Failures are returned as structured
results so the agent can explain the next step to the visitor instead of
pretending an action succeeded.
"""
from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.config import settings
from app.core.security import AutoCRMAuth

logger = logging.getLogger(__name__)

class FrontDeskBackendClient:
    def __init__(self) -> None:
        self.auth = AutoCRMAuth()

    async def _request(self, method: str, path: str, payload: dict | None = None, params: dict | None = None) -> dict:
        headers = await self.auth.get_async_headers()
        url = f"{settings.autocrm_base_url}/api/internal/frontdesk{path}"
        timeout = max(settings.autocrm_auth_timeout, 20)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(method, url, json=payload, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def get_session(self, session_id: UUID | str) -> dict:
        return await self._request("GET", f"/sessions/{session_id}")

    async def save_state(self, session_id: UUID | str, *, state: dict, stage: str | None, summary: str | None, facts: dict) -> dict:
        return await self._request(
            "PUT",
            f"/sessions/{session_id}/state",
            {"state": state, "stage": stage, "summary": summary, "facts": facts},
        )

    async def upsert_lead(self, payload: dict) -> dict:
        return await self._request("POST", "/leads/upsert", payload)

    async def create_handoff(self, payload: dict) -> dict:
        return await self._request("POST", "/handoffs", payload)

    async def list_slots(self, *, day: str, time_zone: str | None = None) -> dict:
        params = {"day": day}
        if time_zone:
            params["time_zone"] = time_zone
        return await self._request("GET", "/slots", params=params)

    async def create_appointment(self, payload: dict) -> dict:
        return await self._request("POST", "/appointments", payload)

    async def create_task(self, payload: dict) -> dict:
        return await self._request("POST", "/tasks", payload)

    async def create_note(self, payload: dict) -> dict:
        return await self._request("POST", "/notes", payload)
