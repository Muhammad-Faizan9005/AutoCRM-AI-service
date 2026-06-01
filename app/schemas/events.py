from __future__ import annotations

from pydantic import BaseModel


class AgentEventIn(BaseModel):
    event_type: str
    entity_id: str
    entity_type: str
    actor_id: str | None = None
    metadata: dict[str, object] | None = None
