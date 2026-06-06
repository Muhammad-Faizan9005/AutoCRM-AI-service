from __future__ import annotations

from pydantic import BaseModel


class AgentRunStatus(BaseModel):
    run_id: str
    status: str
    summary: str | None


class AgentRunTrace(BaseModel):
    step: str
    status: str
    payload: dict[str, object]
