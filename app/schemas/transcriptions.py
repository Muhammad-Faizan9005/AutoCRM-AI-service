from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


RecordingSourceType = Literal["local_path", "url"]
TranscriptStatus = Literal["pending", "processing", "completed", "failed"]


class RecordingReadyIn(BaseModel):
    recording_id: UUID
    meeting_id: UUID | None = None
    entity_id: UUID | None = None
    entity_type: str = Field(default="meeting", max_length=50)
    actor_id: str | None = None
    source_type: RecordingSourceType = "local_path"
    recording_path: str | None = Field(default=None, max_length=1000)
    recording_url: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> "RecordingReadyIn":
        if self.source_type == "local_path" and not self.recording_path:
            raise ValueError("recording_path is required when source_type is local_path")
        if self.source_type == "url" and not self.recording_url:
            raise ValueError("recording_url is required when source_type is url")
        return self


class RecordingReadyResponse(BaseModel):
    status: str
    recording_id: UUID
    job_status: str


class TranscriptJobOut(BaseModel):
    id: UUID | None = None
    recording_id: UUID
    meeting_id: UUID | None = None
    entity_id: UUID | None = None
    entity_type: str | None = None
    source_type: str
    recording_path: str | None = None
    recording_url: str | None = None
    assemblyai_transcript_id: str | None = None
    transcript_text: str | None = None
    status: TranscriptStatus
    attempt_count: int
    max_attempts: int
    error: str | None = None
    last_attempted_at: datetime | None = None
    next_retry_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
