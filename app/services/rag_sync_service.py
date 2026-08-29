from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

from app.config import settings
from app.services.autocrm_client import AutoCRMClient
from app.services.rag_service import RagService


logger = logging.getLogger(__name__)


class RagSyncService:
    SOURCES = ("lead", "deal", "task", "note", "call", "user", "organization", "customer")

    def __init__(self) -> None:
        self.client = AutoCRMClient()
        self.rag = RagService()
        self.state_path = Path(settings.rag_sync_state_file)

    async def run_once(self) -> int:
        state = self._load_state()
        cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}
        indexed_total = 0
        next_cursors = dict(cursors)

        for source in self.SOURCES:
            changed_since = cursors.get(source)
            payload = await self.client.get_rag_snapshot(
                changed_since=str(changed_since) if changed_since else None,
                entity_type=source,
                limit=settings.rag_sync_batch_size,
            )
            documents = payload.get("documents") if isinstance(payload, dict) else []
            if not isinstance(documents, list):
                continue
            indexed, newest = await self._index_documents(documents, current_cursor=changed_since)
            indexed_total += indexed
            if newest:
                next_cursors[source] = newest

        indexed_total += await self._index_frontdesk_knowledge()

        removed = await self.reconcile_deleted_sources()
        if removed:
            logger.info("rag_sync_removed_stale count=%s", removed)
        self._save_state({"cursors": next_cursors})
        return indexed_total

    async def _index_frontdesk_knowledge(self) -> int:
        """Index the local approved front-desk pack into the shared persistent RAG store."""
        root = Path(__file__).resolve().parents[2] / "dev_knowledge"
        if not root.exists():
            return 0
        indexed = 0
        for path in sorted(root.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            await self.rag.add_document(
                entity_id=uuid5(NAMESPACE_URL, f"autocrm:frontdesk:{path.name}"),
                entity_type="frontdesk",
                content=content,
                source="frontdesk_knowledge",
                source_id=path.stem,
                metadata={"scope": "public", "status": "published", "source_table": "frontdesk_knowledge"},
            )
            indexed += 1
        return indexed

    async def reconcile_deleted_sources(self) -> int:
        sources = await self.rag.list_indexed_sources(limit=1000)
        if not sources:
            return 0
        payload = await self.client.reconcile_rag_sources(sources)
        missing = payload.get("missing") if isinstance(payload, dict) else []
        if not isinstance(missing, list):
            return 0
        removed = 0
        for item in missing:
            if not isinstance(item, dict):
                continue
            source_table = str(item.get("source_table") or "").strip()
            source_id = str(item.get("source_id") or "").strip()
            if source_table and source_id:
                removed += await self.rag.delete_source(source_table, source_id)
        return removed

    async def _index_documents(
        self,
        documents: list[object],
        *,
        current_cursor: object,
    ) -> tuple[int, str | None]:
        indexed = 0
        newest = str(current_cursor) if current_cursor else None
        for document in documents:
            if not isinstance(document, dict):
                continue
            try:
                content = str(document.get("content") or "").strip()
                entity_id = UUID(str(document.get("entity_id")))
                if not content:
                    continue
                metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
                await self.rag.add_document(
                    entity_id=entity_id,
                    entity_type=str(document.get("entity_type") or ""),
                    content=content,
                    source=str(document.get("source") or "backend"),
                    source_id=str(document.get("source_id") or ""),
                    metadata={
                        **metadata,
                        "source_id": str(document.get("source_id") or ""),
                        "updated_at": document.get("updated_at"),
                    },
                )
                indexed += 1
                updated_at = document.get("updated_at")
                if updated_at and (newest is None or str(updated_at) > str(newest)):
                    newest = str(updated_at)
                delay = max(0.0, settings.rag_sync_min_delay_seconds)
                if delay:
                    await asyncio.sleep(delay)
            except Exception:
                logger.exception("rag_document_sync_failed document=%s", document)
        return indexed, newest

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                indexed = await self.run_once()
                if indexed:
                    logger.info("rag_sync_indexed count=%s", indexed)
            except Exception:
                logger.exception("rag_sync_failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=max(1, settings.rag_sync_interval_hours) * 3600)
            except asyncio.TimeoutError:
                pass

    def _load_state(self) -> dict[str, object]:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("rag_sync_state_read_failed")
        return {}

    def _save_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
