from __future__ import annotations

from uuid import UUID

from app.services.autocrm_client import AutoCRMClient


class MemoryService:
    def __init__(self) -> None:
        self.client = AutoCRMClient()

    async def get_entity_memory(self, entity_id: UUID, entity_type: str, limit: int = 5) -> list[dict[str, object]]:
        return (await self.client.get_entity_memory(entity_type, entity_id))[:limit]
