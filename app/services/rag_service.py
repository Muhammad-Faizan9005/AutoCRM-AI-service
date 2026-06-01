from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from langchain_core.documents import Document


class RagService:
    def __init__(self) -> None:
        self._store: dict[str, list[Document]] = defaultdict(list)

    async def add_document(self, *, entity_id: UUID, entity_type: str, content: str) -> None:
        key = f"{entity_type}:{entity_id}"
        self._store[key].append(Document(page_content=content))

    async def retrieve(self, *, entity_id: UUID, entity_type: str) -> list[str]:
        key = f"{entity_type}:{entity_id}"
        docs = self._store.get(key, [])
        return [doc.page_content for doc in docs[:5]]
