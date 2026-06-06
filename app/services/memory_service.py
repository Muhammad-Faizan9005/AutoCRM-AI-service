from __future__ import annotations

from uuid import UUID

from app.db.agent_store import AgentStore


class MemoryService:
    def __init__(self) -> None:
        self.store = AgentStore()

    async def get_entity_memory(self, entity_id: UUID, entity_type: str, limit: int = 5) -> list[dict[str, object]]:
        return await self.store.list_recent_entity_actions(entity_id=entity_id, entity_type=entity_type, limit=limit)
