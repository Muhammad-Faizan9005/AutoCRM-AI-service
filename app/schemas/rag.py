from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ContextDocumentIn(BaseModel):
    entity_id: UUID
    entity_type: str
    content: str
    source: str = "manual"
    source_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ContextChunk(BaseModel):
    chunk_id: str
    document_id: str
    entity_id: UUID
    entity_type: str
    content: str
    source: str
    source_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    embedding: list[float]


class RetrievalQuery(BaseModel):
    entity_id: UUID
    entity_type: str
    query: str
    limit: int = 5
    source_filter: str | None = None
    global_search: bool = False
    candidate_entity_ids: list[str] = Field(default_factory=list)
    workflow: str | None = None
    owner_id: str | None = None


class RetrievedContext(BaseModel):
    content: str
    score: float
    source: str
    source_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
