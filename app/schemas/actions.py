from __future__ import annotations

from pydantic import BaseModel


class AgentAction(BaseModel):
    run_id: str | None = None
    action_type: str
    entity_type: str
    entity_id: str
    reason: str
    data: dict[str, object]
    idempotency_key: str | None = None
    requires_approval: bool | None = None
    approval_status: str | None = None
