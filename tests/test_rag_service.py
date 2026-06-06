from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.rag import RetrievalQuery
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RagService, TextChunker
from app.services.vector_store import InMemoryVectorStore


def test_rag_ingests_and_retrieves_relevant_context() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    entity_id = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="lead",
            content="Lead asked about enterprise pricing and implementation timeline.",
            source="note",
            source_id="note-1",
        )
    )
    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="lead",
            content="Support ticket mentioned an unrelated billing issue.",
            source="ticket",
            source_id="ticket-1",
        )
    )

    results = asyncio.run(
        service.retrieve(
            entity_id=entity_id,
            entity_type="lead",
            query="pricing implementation",
            limit=1,
        )
    )

    assert len(results) == 1
    assert "enterprise pricing" in results[0]["content"]
    assert results[0]["source"] == "note"
    assert isinstance(results[0]["score"], float)


def test_rag_chunks_long_documents_with_overlap() -> None:
    chunker = TextChunker(chunk_size=20, overlap=5)
    chunks = chunker.split("0123456789 abcdefghij klmnopqrst")

    assert len(chunks) > 1
    assert chunks[0][-5:] == chunks[1][:5]


def test_rag_source_filter_limits_results() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    entity_id = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="deal",
            content="Manager note says deal is blocked by procurement.",
            source="note",
            source_id="note-2",
        )
    )
    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="deal",
            content="Email thread says legal review is complete.",
            source="email",
            source_id="email-2",
        )
    )

    results = asyncio.run(
        service.retrieve(
            entity_id=entity_id,
            entity_type="deal",
            query="legal review",
            source_filter="email",
        )
    )

    assert results
    assert {result["source"] for result in results} == {"email"}


def test_in_memory_vector_store_scopes_results_by_entity() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    first_entity = uuid4()
    second_entity = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=first_entity,
            entity_type="lead",
            content="First lead wants product demo.",
            source="note",
        )
    )
    asyncio.run(
        service.add_document(
            entity_id=second_entity,
            entity_type="lead",
            content="Second lead wants pricing.",
            source="note",
        )
    )

    first_results = asyncio.run(
        service.retrieve(entity_id=first_entity, entity_type="lead", query="pricing demo")
    )

    assert first_results
    assert all("Second lead" not in result["content"] for result in first_results)
