from __future__ import annotations

import asyncio
from uuid import uuid4

from app.services import context_service as context_module
from app.services.context_service import ContextService


def test_context_includes_snapshot_and_memory(monkeypatch) -> None:
    captured = {}

    async def fake_retrieve(self, *, entity_id, entity_type, query=None, limit=5, source_filter=None, **kwargs):
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
    assert context["rag_docs"][0]["content"] == "doc1"
    assert "stale_lead" in captured["query"]
    assert "Lead A" in captured["query"]
    assert "pricing discussion" in captured["query"]


def test_daily_summary_uses_owner_scoped_global_rag(monkeypatch) -> None:
    captured = {}

    async def fake_retrieve(self, **kwargs):
        captured.update(kwargs)
        return [{"content": "Lead needs proposal", "source": "backend.lead"}]

    async def fake_snapshot(self, entity_id, entity_type):
        return {"id": str(entity_id), "full_name": "Manager A"}

    async def fake_memory(self, entity_id, entity_type, limit=5):
        return []

    async def fake_leads(self):
        return [{"id": str(uuid4()), "owner_id": captured["owner"], "name": "Lead A"}]

    async def fake_deals(self):
        return [{"id": str(uuid4()), "owner_id": captured["owner"], "stage": "proposal"}]

    monkeypatch.setattr(context_module.RagService, "retrieve", fake_retrieve)
    monkeypatch.setattr(context_module.ToolRegistry, "fetch_entity_snapshot", fake_snapshot)
    monkeypatch.setattr(context_module.MemoryService, "get_entity_memory", fake_memory)
    monkeypatch.setattr(context_module.AutoCRMClient, "list_leads", fake_leads)
    monkeypatch.setattr(context_module.AutoCRMClient, "list_deals", fake_deals)

    service = ContextService()
    user_id = uuid4()
    captured["owner"] = str(user_id)

    context = asyncio.run(
        service.build_context(
            entity_id=user_id,
            entity_type="user",
            event_type="daily_summary",
        )
    )

    assert captured["global_search"] is True
    assert captured["owner_id"] == str(user_id)
    assert captured["workflow"] == "daily_summary"
    assert context["owned_leads"][0]["name"] == "Lead A"
    assert context["owned_deals"][0]["stage"] == "proposal"
