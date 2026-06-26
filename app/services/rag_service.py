from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from app.config import settings
from app.schemas.rag import ContextChunk, ContextDocumentIn, RetrievalQuery, RetrievedContext
from app.services.embedding_service import EmbeddingService, build_embedding_service
from app.services.vector_store import VectorStore, build_vector_store


class TextChunker:
    def __init__(self, chunk_size: int = 900, overlap: int = 120) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        if len(normalized) <= self.chunk_size:
            return [normalized]

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.chunk_size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(end - self.overlap, start + 1)
        return chunks


class RagService:
    def __init__(
        self,
        *,
        vector_store: VectorStore | None = None,
        embeddings: EmbeddingService | None = None,
        chunker: TextChunker | None = None,
    ) -> None:
        self.vector_store = vector_store or build_vector_store(settings.vector_store)
        self.embeddings = embeddings or build_embedding_service()
        self.chunker = chunker or TextChunker(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        )

    async def add_document(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        content: str,
        source: str = "manual",
        source_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        document = ContextDocumentIn(
            entity_id=entity_id,
            entity_type=entity_type,
            content=content,
            source=source,
            source_id=source_id,
            metadata=metadata or {},
        )
        document_id = self._document_id(document)
        await self.vector_store.delete_document(document_id)
        chunks = await self._build_chunks(document, document_id)
        await self.vector_store.upsert_chunks(chunks)
        return document_id

    async def retrieve(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        query: str | None = None,
        limit: int = 5,
        source_filter: str | None = None,
        global_search: bool = False,
        candidate_entity_ids: list[str] | None = None,
        workflow: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict[str, object]]:
        retrieval_query = RetrievalQuery(
            entity_id=entity_id,
            entity_type=entity_type,
            query=query or f"{entity_type} {entity_id}",
            limit=limit,
            source_filter=source_filter,
            global_search=global_search,
            candidate_entity_ids=candidate_entity_ids or [],
            workflow=workflow,
            owner_id=owner_id,
        )
        query_embedding = await self.embeddings.embed(retrieval_query.query)
        results = await self.vector_store.similarity_search(retrieval_query, query_embedding)
        return [self._serialize_result(result) for result in results]

    async def list_indexed_sources(self, limit: int = 1000) -> list[dict[str, str]]:
        return await self.vector_store.list_indexed_sources(limit=limit)

    async def delete_source(self, source_table: str, source_id: str) -> int:
        return await self.vector_store.delete_source(source_table, source_id)

    async def _build_chunks(self, document: ContextDocumentIn, document_id: str) -> list[ContextChunk]:
        chunks: list[ContextChunk] = []
        for index, content in enumerate(self.chunker.split(document.content)):
            embedding = await self.embeddings.embed(content)
            chunks.append(
                ContextChunk(
                    chunk_id=f"{document_id}:{index}",
                    document_id=document_id,
                    entity_id=document.entity_id,
                    entity_type=document.entity_type,
                    content=content,
                    source=document.source,
                    source_id=document.source_id,
                    metadata={**document.metadata, "chunk_index": index},
                    embedding=embedding,
                )
            )
        return chunks

    def _document_id(self, document: ContextDocumentIn) -> str:
        stable = f"{document.entity_type}:{document.entity_id}:{document.source}:{document.source_id}:{document.content}"
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        if document.source_id:
            source_key = f"{document.entity_type}:{document.entity_id}:{document.source}:{document.source_id}"
            source_digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:32]
            return f"doc_{source_digest}"
        return f"doc_{digest}_{uuid4().hex[:8]}"

    def _serialize_result(self, result: RetrievedContext) -> dict[str, object]:
        return result.model_dump(mode="json")
