from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AgentAction(BaseModel):
    run_id: str | None = None
    action_type: str
    entity_type: str
    entity_id: UUID
    reason: str
    data: dict[str, object]
    idempotency_key: str | None = None
    requires_approval: bool | None = None
    approval_status: str | None = None
