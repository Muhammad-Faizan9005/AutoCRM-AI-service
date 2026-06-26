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


def test_rag_global_search_can_retrieve_owned_context_across_entities() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    user_id = uuid4()
    first_entity = uuid4()
    second_entity = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=first_entity,
            entity_type="lead",
            content="Lead needs enterprise security review.",
            source="backend.lead",
            source_id="lead-1",
            metadata={"owner_id": str(user_id), "source_table": "lead"},
        )
    )
    asyncio.run(
        service.add_document(
            entity_id=second_entity,
            entity_type="deal",
            content="Deal is blocked by legal review.",
            source="backend.deal",
            source_id="deal-1",
            metadata={"owner_id": str(user_id), "source_table": "deal"},
        )
    )

    results = asyncio.run(
        service.retrieve(
            entity_id=user_id,
            entity_type="user",
            query="security legal review",
            global_search=True,
            owner_id=str(user_id),
            workflow="daily_summary",
            limit=5,
        )
    )

    assert len(results) == 2
    assert {result["source"] for result in results} == {"backend.lead", "backend.deal"}


def test_rag_replaces_document_chunks_on_update() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    entity_id = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="lead",
            content="Old pricing objection.",
            source="backend.lead",
            source_id="lead-1",
        )
    )
    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="lead",
            content="New implementation timeline discussion.",
            source="backend.lead",
            source_id="lead-1",
        )
    )

    results = asyncio.run(service.retrieve(entity_id=entity_id, entity_type="lead", query="pricing implementation", limit=5))

    assert any("New implementation" in result["content"] for result in results)
    assert all("Old pricing" not in result["content"] for result in results)


def test_rag_deletes_indexed_source() -> None:
    store = InMemoryVectorStore()
    store.clear()
    service = RagService(vector_store=store, embeddings=EmbeddingService(), chunker=TextChunker())
    entity_id = uuid4()

    asyncio.run(
        service.add_document(
            entity_id=entity_id,
            entity_type="lead",
            content="Lead should disappear after deletion.",
            source="backend.lead",
            source_id="lead-delete-1",
            metadata={"source_table": "lead", "source_id": "lead-delete-1"},
        )
    )

    removed = asyncio.run(service.delete_source("lead", "lead-delete-1"))
    results = asyncio.run(service.retrieve(entity_id=entity_id, entity_type="lead", query="disappear", limit=5))

    assert removed > 0
    assert results == []
