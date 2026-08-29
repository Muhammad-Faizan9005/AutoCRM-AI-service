from __future__ import annotations

from collections import defaultdict
import asyncio
import pickle
from pathlib import Path
from uuid import UUID

import numpy as np

from app.config import settings
from app.db.pool import get_pool
from app.schemas.rag import ContextChunk, RetrievalQuery, RetrievedContext
from app.services.embedding_service import cosine_similarity


class VectorStore:
    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        raise NotImplementedError

    async def delete_document(self, document_id: str) -> None:
        raise NotImplementedError

    async def list_indexed_sources(self, limit: int = 1000) -> list[dict[str, str]]:
        raise NotImplementedError

    async def delete_source(self, source_table: str, source_id: str) -> int:
        raise NotImplementedError

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        raise NotImplementedError


_VECTOR_STORE_CACHE: dict[str, VectorStore] = {}


class InMemoryVectorStore(VectorStore):
    _chunks_by_entity: dict[str, list[ContextChunk]] = defaultdict(list)

    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        for chunk in chunks:
            key = self._key(chunk.entity_id, chunk.entity_type)
            existing = [item for item in self._chunks_by_entity[key] if item.chunk_id != chunk.chunk_id]
            existing.append(chunk)
            self._chunks_by_entity[key] = existing

    async def delete_document(self, document_id: str) -> None:
        for key, chunks in list(self._chunks_by_entity.items()):
            kept = [chunk for chunk in chunks if chunk.document_id != document_id]
            if kept:
                self._chunks_by_entity[key] = kept
            else:
                self._chunks_by_entity.pop(key, None)

    async def list_indexed_sources(self, limit: int = 1000) -> list[dict[str, str]]:
        seen = {}
        for chunks in self._chunks_by_entity.values():
            for chunk in chunks:
                source_table = str(chunk.metadata.get("source_table") or "").strip()
                source_id = str(chunk.metadata.get("source_id") or chunk.source_id or "").strip()
                if source_table and source_id:
                    seen[(source_table, source_id)] = {"source_table": source_table, "source_id": source_id}
                if len(seen) >= limit:
                    return list(seen.values())
        return list(seen.values())

    async def delete_source(self, source_table: str, source_id: str) -> int:
        removed = 0
        for key, chunks in list(self._chunks_by_entity.items()):
            kept = []
            for chunk in chunks:
                if str(chunk.metadata.get("source_table") or "") == source_table and str(chunk.metadata.get("source_id") or chunk.source_id or "") == source_id:
                    removed += 1
                else:
                    kept.append(chunk)
            if kept:
                self._chunks_by_entity[key] = kept
            else:
                self._chunks_by_entity.pop(key, None)
        return removed

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        if query.global_search:
            candidates = [chunk for chunks in self._chunks_by_entity.values() for chunk in chunks]
        else:
            key = self._key(query.entity_id, query.entity_type)
            candidates = self._chunks_by_entity.get(key, [])
        if query.source_filter:
            candidates = [chunk for chunk in candidates if chunk.source == query.source_filter]
        if query.candidate_entity_ids:
            candidate_ids = set(query.candidate_entity_ids)
            candidates = [chunk for chunk in candidates if str(chunk.entity_id) in candidate_ids]
        if query.owner_id:
            candidates = [chunk for chunk in candidates if str(chunk.metadata.get("owner_id") or "") == query.owner_id]

        ranked = sorted(
            candidates,
            key=lambda chunk: self._boost_score(chunk, query, cosine_similarity(query_embedding, chunk.embedding)),
            reverse=True,
        )
        return [
            RetrievedContext(
                content=chunk.content,
                score=self._boost_score(chunk, query, cosine_similarity(query_embedding, chunk.embedding)),
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

    def _boost_score(self, chunk: ContextChunk, query: RetrievalQuery, score: float) -> float:
        if chunk.entity_id == query.entity_id and chunk.entity_type == query.entity_type:
            return score + 0.20
        return score


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

    async def delete_document(self, document_id: str) -> None:
        await get_pool().execute("DELETE FROM ai_context_chunks WHERE document_id=$1", document_id)

    async def list_indexed_sources(self, limit: int = 1000) -> list[dict[str, str]]:
        rows = await get_pool().fetch(
            """
            SELECT DISTINCT metadata->>'source_table' AS source_table,
                            COALESCE(metadata->>'source_id', source_id) AS source_id
            FROM ai_context_chunks
            WHERE metadata ? 'source_table'
            LIMIT $1
            """,
            limit,
        )
        return [
            {"source_table": str(row["source_table"]), "source_id": str(row["source_id"])}
            for row in rows
            if row["source_table"] and row["source_id"]
        ]

    async def delete_source(self, source_table: str, source_id: str) -> int:
        result = await get_pool().execute(
            """
            DELETE FROM ai_context_chunks
            WHERE metadata->>'source_table'=$1
              AND COALESCE(metadata->>'source_id', source_id)=$2
            """,
            source_table,
            source_id,
        )
        try:
            return int(str(result).split()[-1])
        except Exception:
            return 0

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        clauses = []
        args: list[object] = [
            self._vector_literal(query_embedding),
            query.limit,
        ]
        if not query.global_search:
            clauses.append(f"entity_id=${len(args) + 1}::uuid")
            args.append(query.entity_id)
            clauses.append(f"entity_type=${len(args) + 1}")
            args.append(query.entity_type)
        if query.source_filter:
            clauses.append(f"source=${len(args) + 1}")
            args.append(query.source_filter)
        if query.owner_id:
            clauses.append(f"metadata->>'owner_id'=${len(args) + 1}")
            args.append(query.owner_id)
        if query.candidate_entity_ids:
            clauses.append(f"entity_id::text = ANY(${len(args) + 1}::text[])")
            args.append(query.candidate_entity_ids)
        where_clause = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            "SELECT content, source, source_id, metadata, 1 - (embedding <=> $1::vector) AS score "
            "FROM ai_context_chunks "
            f"{where_clause} "
            "ORDER BY embedding <=> $1::vector LIMIT $2"
        )
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
    cache_key = f"{normalized}:{Path(settings.rag_index_dir).resolve()}" if normalized == "faiss" else normalized
    cached = _VECTOR_STORE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if normalized == "faiss":
        store = FaissVectorStore(Path(settings.rag_index_dir))
    elif normalized in {"pgvector", "postgres", "postgresql"}:
        store = PgVectorStore()
    else:
        store = InMemoryVectorStore()
    _VECTOR_STORE_CACHE[cache_key] = store
    return store


class FaissVectorStore(VectorStore):
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir
        self.index_path = index_dir / "context.index"
        self.metadata_path = index_dir / "context_chunks.pkl"
        self._lock = asyncio.Lock()
        self._chunks: dict[str, ContextChunk] = {}
        self._chunk_ids: list[str] = []
        self._index = None
        self._load()

    async def upsert_chunks(self, chunks: list[ContextChunk]) -> None:
        if not chunks:
            return
        async with self._lock:
            for chunk in chunks:
                self._chunks[chunk.chunk_id] = chunk
            self._rebuild_index()
            self._persist()

    async def delete_document(self, document_id: str) -> None:
        async with self._lock:
            removed = False
            for chunk_id, chunk in list(self._chunks.items()):
                if chunk.document_id == document_id:
                    self._chunks.pop(chunk_id, None)
                    removed = True
            if removed:
                self._rebuild_index()
                self._persist()

    async def list_indexed_sources(self, limit: int = 1000) -> list[dict[str, str]]:
        async with self._lock:
            seen = {}
            for chunk in self._chunks.values():
                source_table = str(chunk.metadata.get("source_table") or "").strip()
                source_id = str(chunk.metadata.get("source_id") or chunk.source_id or "").strip()
                if source_table and source_id:
                    seen[(source_table, source_id)] = {"source_table": source_table, "source_id": source_id}
                if len(seen) >= limit:
                    return list(seen.values())
            return list(seen.values())

    async def delete_source(self, source_table: str, source_id: str) -> int:
        async with self._lock:
            removed = 0
            for chunk_id, chunk in list(self._chunks.items()):
                if (
                    str(chunk.metadata.get("source_table") or "") == source_table
                    and str(chunk.metadata.get("source_id") or chunk.source_id or "") == source_id
                ):
                    self._chunks.pop(chunk_id, None)
                    removed += 1
            if removed:
                self._rebuild_index()
                self._persist()
            return removed

    async def similarity_search(self, query: RetrievalQuery, query_embedding: list[float]) -> list[RetrievedContext]:
        async with self._lock:
            if self._index is None or not self._chunks:
                return []
            query_vector = np.asarray([query_embedding], dtype="float32")
            try:
                import faiss

                search_limit = min(len(self._chunk_ids), max(query.limit * 12, 50))
                scores, indices = self._index.search(query_vector, search_limit)
            except Exception:
                ranked = self._rank_candidates(
                    list(self._chunks.values()),
                    query=query,
                    query_embedding=query_embedding,
                )
                return [self._to_result(chunk, score) for chunk, score in ranked[: query.limit]]

            ranked: list[tuple[ContextChunk, float]] = []
            for score, index in zip(scores[0], indices[0]):
                if index < 0:
                    continue
                chunk_id = self._chunk_ids[int(index)]
                chunk = self._chunks.get(chunk_id)
                if chunk is None or not self._matches_query_scope(chunk, query):
                    continue
                ranked.append((chunk, self._boost_score(chunk, query, float(score))))
            ranked.sort(key=lambda item: item[1], reverse=True)
            return [self._to_result(chunk, score) for chunk, score in ranked[: query.limit]]

    def _load(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if self.metadata_path.exists():
            with self.metadata_path.open("rb") as handle:
                data = pickle.load(handle)
                self._chunks = data if isinstance(data, dict) else {}
        self._chunk_ids = list(self._chunks.keys())
        if self.index_path.exists() and self._chunk_ids:
            try:
                import faiss

                loaded = faiss.read_index(str(self.index_path))
                if loaded.ntotal == len(self._chunk_ids):
                    self._index = loaded
                    return
            except Exception:
                pass
        self._rebuild_index()

    def _persist(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with self.metadata_path.open("wb") as handle:
            pickle.dump(self._chunks, handle)
        if self._index is not None:
            try:
                import faiss

                faiss.write_index(self._index, str(self.index_path))
            except Exception:
                pass

    def _rebuild_index(self) -> None:
        if not self._chunks:
            self._index = None
            self._chunk_ids = []
            return
        self._chunk_ids = list(self._chunks.keys())
        matrix = np.asarray([self._chunks[chunk_id].embedding for chunk_id in self._chunk_ids], dtype="float32")
        try:
            import faiss

            self._index = faiss.IndexFlatIP(matrix.shape[1])
            self._index.add(matrix)
        except Exception:
            self._index = None

    def _rank_candidates(
        self,
        candidates: list[ContextChunk],
        *,
        query: RetrievalQuery,
        query_embedding: list[float],
    ) -> list[tuple[ContextChunk, float]]:
        ranked = [
            (chunk, self._boost_score(chunk, query, cosine_similarity(query_embedding, chunk.embedding)))
            for chunk in candidates
            if self._matches_query_scope(chunk, query)
        ]
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _matches_query_scope(self, chunk: ContextChunk, query: RetrievalQuery) -> bool:
        if query.source_filter and chunk.source != query.source_filter:
            return False
        if query.candidate_entity_ids and str(chunk.entity_id) not in set(query.candidate_entity_ids):
            return False
        if query.owner_id and str(chunk.metadata.get("owner_id") or "") != query.owner_id:
            return False
        if not query.global_search:
            return chunk.entity_id == query.entity_id and chunk.entity_type == query.entity_type
        return True

    def _boost_score(self, chunk: ContextChunk, query: RetrievalQuery, score: float) -> float:
        boosted = score
        if chunk.entity_id == query.entity_id and chunk.entity_type == query.entity_type:
            boosted += 0.20
        if query.workflow and str(chunk.metadata.get("source_table") or "") in self._preferred_sources(query.workflow):
            boosted += 0.08
        return boosted

    def _preferred_sources(self, workflow: str) -> set[str]:
        return {
            "daily_summary": {"lead", "deal", "task", "note", "call"},
            "lead_nudge": {"lead", "task", "note", "call"},
            "stale_lead": {"lead", "task", "note", "call"},
            "deal_risk": {"deal", "note", "task"},
            "meeting_intel": {"call", "note", "task"},
            "task_auto": {"task", "lead", "deal", "note"},
        }.get(workflow, set())

    def _to_result(self, chunk: ContextChunk, score: float) -> RetrievedContext:
        return RetrievedContext(
            content=chunk.content,
            score=score,
            source=chunk.source,
            source_id=chunk.source_id,
            metadata=chunk.metadata,
        )
