from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.db.pool import get_pool
from app.schemas.rag import ContextChunk, RetrievalQuery, RetrievedContext
from app.services.embedding_service import cosine_similarity


class VectorStore:
    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        raise NotImplementedError

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    _chunks_by_entity: dict[str, list[ContextChunk]] = defaultdict(list)

    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        for chunk in chunks:
            key = self._key(chunk.entity_id, chunk.entity_type)
            existing = [item for item in self._chunks_by_entity[key] if item.chunk_id != chunk.chunk_id]
            existing.append(chunk)
            self._chunks_by_entity[key] = existing

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        key = self._key(query.entity_id, query.entity_type)
        candidates = self._chunks_by_entity.get(key, [])
        if query.source_filter:
            candidates = [chunk for chunk in candidates if chunk.source == query.source_filter]

        ranked = sorted(
            candidates,
            key=lambda chunk: cosine_similarity(query_embedding, chunk.embedding),
            reverse=True,
        )
        return [
            RetrievedContext(
                content=chunk.content,
                score=cosine_similarity(query_embedding, chunk.embedding),
                source=chunk.source,
                source_id=chunk.source_id,
                metadata=chunk.metadata,
            )
            for chunk in ranked[: query.limit]
        ]

    def clear(self) -> None:
        self._chunks_by_entity.clear()

    def _key(self, entity_id: UUID, entity_type: str) -> str:
        return f"{entity_type.strip().lower()}:{entity_id}"


class PgVectorStore(VectorStore):
    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        query = (
            "INSERT INTO ai_context_chunks "
            "(id, document_id, entity_id, entity_type, content, source, source_id, metadata, embedding) "
            "VALUES ($1, $2, $3::uuid, $4, $5, $6, $7, $8::jsonb, $9::vector) "
            "ON CONFLICT (id) DO UPDATE SET content=EXCLUDED.content, metadata=EXCLUDED.metadata, embedding=EXCLUDED.embedding"
        )
        for chunk in chunks:
            await get_pool().execute(
                query,
                chunk.chunk_id,
                chunk.document_id,
                chunk.entity_id,
                chunk.entity_type,
                chunk.content,
                chunk.source,
                chunk.source_id,
                self._json(chunk.metadata),
                self._vector_literal(chunk.embedding),
            )

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        source_clause = "AND source=$5" if query.source_filter else ""
        sql = (
            "SELECT content, source, source_id, metadata, 1 - (embedding <=> $1::vector) AS score "
            "FROM ai_context_chunks "
            f"WHERE entity_id=$2::uuid AND entity_type=$3 {source_clause} "
            "ORDER BY embedding <=> $1::vector LIMIT $4"
        )
        args: list[object] = [
            self._vector_literal(query_embedding),
            query.entity_id,
            query.entity_type,
            query.limit,
        ]
        if query.source_filter:
            args.append(query.source_filter)
        rows = await get_pool().fetch(sql, *args)
        return [
            RetrievedContext(
                content=str(row["content"]),
                score=float(row["score"] or 0.0),
                source=str(row["source"]),
                source_id=row["source_id"],
                metadata=dict(row["metadata"] or {}),
            )
            for row in rows
        ]

    def _vector_literal(self, embedding: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"

    def _json(self, payload: dict[str, object]) -> str:
        import json

        return json.dumps(payload, default=str)


def build_vector_store(kind: str) -> VectorStore:
    normalized = kind.strip().lower()
    if normalized in {"pgvector", "postgres", "postgresql"}:
        return PgVectorStore()
    return InMemoryVectorStore()
