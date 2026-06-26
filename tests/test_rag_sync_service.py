from __future__ import annotations

import asyncio
from uuid import uuid4

from app.services import rag_sync_service as sync_module
from app.services.rag_sync_service import RagSyncService


def test_rag_sync_uses_per_source_cursors(monkeypatch, tmp_path) -> None:
    calls = []
    indexed = []

    async def fake_snapshot(self, *, changed_since=None, entity_type=None, limit=None):
        calls.append({"entity_type": entity_type, "changed_since": changed_since})
        return {
            "documents": [
                {
                    "entity_type": "lead" if entity_type == "lead" else "user",
                    "entity_id": str(uuid4()),
                    "source": f"backend.{entity_type}",
                    "source_id": f"{entity_type}-1",
                    "content": f"{entity_type} content",
                    "updated_at": f"2026-06-26T00:00:0{len(calls)}+00:00",
                    "metadata": {"source_table": entity_type, "owner_id": str(uuid4())},
                }
            ]
        }

    async def fake_add_document(self, **kwargs):
        indexed.append(kwargs)
        return "doc"

    async def fake_list_sources(self, limit=1000):
        return []

    monkeypatch.setattr(sync_module.settings, "rag_sync_state_file", str(tmp_path / "rag_state.json"))
    monkeypatch.setattr(sync_module.settings, "rag_sync_batch_size", 10)
    monkeypatch.setattr(sync_module.settings, "rag_sync_min_delay_seconds", 0)
    monkeypatch.setattr(sync_module.AutoCRMClient, "get_rag_snapshot", fake_snapshot)
    monkeypatch.setattr(sync_module.RagService, "add_document", fake_add_document)
    monkeypatch.setattr(sync_module.RagService, "list_indexed_sources", fake_list_sources)

    count = asyncio.run(RagSyncService().run_once())

    assert count == len(RagSyncService.SOURCES)
    assert [call["entity_type"] for call in calls] == list(RagSyncService.SOURCES)
    assert all(call["changed_since"] is None for call in calls)
    assert len(indexed) == len(RagSyncService.SOURCES)


def test_rag_sync_reconciles_deleted_sources(monkeypatch, tmp_path) -> None:
    deleted = []

    async def fake_list_sources(self, limit=1000):
        return [{"source_table": "lead", "source_id": "missing-lead"}]

    async def fake_reconcile(self, sources):
        return {"missing": sources, "checked": len(sources)}

    async def fake_delete_source(self, source_table, source_id):
        deleted.append((source_table, source_id))
        return 2

    monkeypatch.setattr(sync_module.settings, "rag_sync_state_file", str(tmp_path / "rag_state.json"))
    monkeypatch.setattr(sync_module.RagService, "list_indexed_sources", fake_list_sources)
    monkeypatch.setattr(sync_module.AutoCRMClient, "reconcile_rag_sources", fake_reconcile)
    monkeypatch.setattr(sync_module.RagService, "delete_source", fake_delete_source)

    removed = asyncio.run(RagSyncService().reconcile_deleted_sources())

    assert removed == 2
    assert deleted == [("lead", "missing-lead")]
