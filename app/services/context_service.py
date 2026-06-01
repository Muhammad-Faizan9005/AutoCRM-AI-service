from __future__ import annotations

from uuid import UUID

from app.services.rag_service import RagService


class ContextService:
    def __init__(self) -> None:
        self.rag = RagService()

    async def build_context(self, entity_id: UUID, entity_type: str) -> dict[str, object]:
        # Placeholder for structured DB fetch + RAG enrichment.
        rag_docs = await self.rag.retrieve(entity_id=entity_id, entity_type=entity_type)
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "rag_docs": rag_docs,
        }
