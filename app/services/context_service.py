from __future__ import annotations

from uuid import UUID

from app.services.memory_service import MemoryService
from app.services.rag_service import RagService
from app.services.tool_registry import ToolRegistry


class ContextService:
    def __init__(self) -> None:
        self.rag = RagService()
        self.memory = MemoryService()
        self.tools = ToolRegistry()

    async def build_context(
        self,
        entity_id: UUID,
        entity_type: str,
        *,
        event_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        entity_snapshot = await self.tools.fetch_entity_snapshot(entity_id=entity_id, entity_type=entity_type)
        entity_memory = await self.memory.get_entity_memory(entity_id=entity_id, entity_type=entity_type)
        retrieval_query = self._build_retrieval_query(
            entity_type=entity_type,
            event_type=event_type,
            metadata=metadata or {},
            entity_snapshot=entity_snapshot,
            entity_memory=entity_memory,
        )
        rag_docs = await self.rag.retrieve(
            entity_id=entity_id,
            entity_type=entity_type,
            query=retrieval_query,
        )
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "retrieval_query": retrieval_query,
            "entity_snapshot": entity_snapshot,
            "entity_memory": entity_memory,
            "rag_docs": rag_docs,
        }

    def _build_retrieval_query(
        self,
        *,
        entity_type: str,
        event_type: str | None,
        metadata: dict[str, object],
        entity_snapshot: dict[str, object],
        entity_memory: list[dict[str, object]],
    ) -> str:
        snapshot_terms = " ".join(
            str(value)
            for key, value in entity_snapshot.items()
            if key in {"name", "title", "status", "stage", "company", "email"} and value
        )
        memory_terms = " ".join(
            f"{item.get('action_type', '')} {item.get('reason', '')}"
            for item in entity_memory[:3]
        )
        metadata_terms = " ".join(str(value) for value in metadata.values() if isinstance(value, str))
        return " ".join(
            part
            for part in [event_type or "", entity_type, snapshot_terms, memory_terms, metadata_terms]
            if part
        )
