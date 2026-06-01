from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.services.run_manager import RunContext


class BaseWorkflow:
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        raise NotImplementedError
