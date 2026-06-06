from __future__ import annotations

import asyncio
from uuid import uuid4

from app.services import context_service as context_module
from app.services.context_service import ContextService


def test_context_includes_snapshot_and_memory(monkeypatch) -> None:
    captured = {}

    async def fake_retrieve(self, *, entity_id, entity_type, query=None, limit=5, source_filter=None):
        captured["query"] = query
        return ["doc1"]

    async def fake_snapshot(self, entity_id, entity_type):
        return {"id": str(entity_id), "name": "Lead A"}

    async def fake_memory(self, entity_id, entity_type, limit=5):
        return [{"action_type": "create_task", "reason": "old"}]

    monkeypatch.setattr(context_module.RagService, "retrieve", fake_retrieve)
    monkeypatch.setattr(context_module.ToolRegistry, "fetch_entity_snapshot", fake_snapshot)
    monkeypatch.setattr(context_module.MemoryService, "get_entity_memory", fake_memory)

    service = ContextService()
    entity_id = uuid4()

    context = asyncio.run(
        service.build_context(
            entity_id=entity_id,
            entity_type="lead",
            event_type="stale_lead",
            metadata={"note": "pricing discussion"},
        )
    )

    assert context["entity_snapshot"]["name"] == "Lead A"
    assert context["entity_memory"][0]["action_type"] == "create_task"
    assert context["rag_docs"] == ["doc1"]
    assert "stale_lead" in captured["query"]
    assert "Lead A" in captured["query"]
    assert "pricing discussion" in captured["query"]
