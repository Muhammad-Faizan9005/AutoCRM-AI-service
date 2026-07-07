from __future__ import annotations

from uuid import UUID

from app.config import settings
from app.services.autocrm_client import AutoCRMClient
from app.services.memory_service import MemoryService
from app.services.rag_service import RagService
from app.services.tool_registry import ToolRegistry


class ContextService:
    def __init__(self) -> None:
        self.rag = RagService()
        self.memory = MemoryService()
        self.tools = ToolRegistry()
        self.client = AutoCRMClient()

    async def build_context(
        self,
        entity_id: UUID,
        entity_type: str,
        *,
        event_type: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if event_type == "daily_summary" and entity_type.strip().lower() in {"user", "agent"}:
            return await self._build_daily_summary_context(
                entity_id=entity_id,
                entity_type=entity_type,
                event_type=event_type,
                metadata=metadata or {},
            )

        entity_snapshot = await self.tools.fetch_entity_snapshot(entity_id=entity_id, entity_type=entity_type)
        entity_memory = await self.memory.get_entity_memory(entity_id=entity_id, entity_type=entity_type)
        retrieval_query = self._build_retrieval_query(
            entity_type=entity_type,
            event_type=event_type,
            metadata=metadata or {},
            entity_snapshot=entity_snapshot,
            entity_memory=entity_memory,
        )
        candidate_entity_ids = self._candidate_entity_ids(entity_id, entity_snapshot)
        rag_docs = await self.rag.retrieve(
            entity_id=entity_id,
            entity_type=entity_type,
            query=retrieval_query,
            limit=settings.rag_top_k,
            workflow=event_type,
            global_search=len(candidate_entity_ids) > 1,
            candidate_entity_ids=candidate_entity_ids,
        )
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "retrieval_query": retrieval_query,
            "entity_snapshot": entity_snapshot,
            "entity_memory": entity_memory,
            "rag_docs": self._budget_rag_docs(rag_docs),
        }

    async def _build_daily_summary_context(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        event_type: str,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        user_snapshot = await self.tools.fetch_entity_snapshot(entity_id=entity_id, entity_type=entity_type)
        user_memory = await self.memory.get_entity_memory(entity_id=entity_id, entity_type=entity_type)
        summary_context = await self.client.get_user_summary_context(entity_id)
        owned_leads = summary_context.get("owned_leads") if isinstance(summary_context.get("owned_leads"), list) else []
        owned_deals = summary_context.get("owned_deals") if isinstance(summary_context.get("owned_deals"), list) else []
        retrieval_query = self._build_retrieval_query(
            entity_type=entity_type,
            event_type=event_type,
            metadata={
                **metadata,
                "owned_leads": " ".join(str(item.get("name") or item.get("company") or "") for item in owned_leads[:10]),
                "owned_deals": " ".join(str(item.get("stage") or item.get("title") or "") for item in owned_deals[:10]),
            },
            entity_snapshot=user_snapshot,
            entity_memory=user_memory,
        )
        rag_docs = await self.rag.retrieve(
            entity_id=entity_id,
            entity_type="user",
            query=retrieval_query,
            limit=max(settings.rag_top_k, 10),
            global_search=True,
            workflow="daily_summary",
            owner_id=str(entity_id),
        )
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "retrieval_query": retrieval_query,
            "entity_snapshot": user_snapshot,
            "entity_memory": user_memory,
            "owned_leads": self._compact_items(owned_leads, limit=20),
            "owned_deals": self._compact_items(owned_deals, limit=20),
            "rag_docs": self._budget_rag_docs(rag_docs, max_docs=10, max_content_chars=700),
        }

    async def _owned_items(self, loader, owner_id: UUID) -> list[dict[str, object]]:
        try:
            items = await loader()
        except Exception:
            return []
        owner = str(owner_id)
        return [
            item
            for item in items
            if str(item.get("owner_id") or item.get("assigned_to") or item.get("id") or "") == owner
        ]

    def _compact_items(self, items: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
        compacted = []
        for item in items[:limit]:
            compacted.append(
                {
                    key: value
                    for key, value in item.items()
                    if key
                    in {
                        "id",
                        "name",
                        "title",
                        "company",
                        "email",
                        "status",
                        "stage",
                        "score",
                        "score_reason",
                        "value",
                        "expected_close_at",
                        "updated_at",
                    }
                    and value is not None
                }
            )
        return compacted

    def _candidate_entity_ids(self, entity_id: UUID, entity_snapshot: dict[str, object]) -> list[str]:
        candidates = [str(entity_id)]
        for key in ("organization_id", "customer_id", "lead_id"):
            value = entity_snapshot.get(key)
            if value and str(value) not in candidates:
                candidates.append(str(value))
        return candidates

    def _budget_rag_docs(
        self,
        rag_docs: list[dict[str, object]],
        *,
        max_docs: int | None = None,
        max_content_chars: int = 900,
    ) -> list[dict[str, object]]:
        docs = []
        for doc in rag_docs[: max_docs or settings.rag_top_k]:
            if not isinstance(doc, dict):
                docs.append({"content": str(doc), "score": 0.0, "source": "unknown", "metadata": {}})
                continue
            content = str(doc.get("content") or "")
            docs.append(
                {
                    **doc,
                    "content": content if len(content) <= max_content_chars else f"{content[:max_content_chars].rstrip()}...",
                }
            )
        return docs

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
