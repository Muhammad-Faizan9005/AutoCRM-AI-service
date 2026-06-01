from __future__ import annotations

from pydantic import BaseModel


class AgentRunStatus(BaseModel):
    run_id: str
    status: str
    summary: str | None
