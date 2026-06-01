from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AgentEventIn(BaseModel):
    event_type: str
    entity_id: UUID
    entity_type: str
    actor_id: str | None = None
    metadata: dict[str, object] | None = None
