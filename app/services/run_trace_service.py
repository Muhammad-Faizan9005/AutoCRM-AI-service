from __future__ import annotations

from uuid import UUID

from app.db.agent_store import AgentStore


class RunTraceService:
    def __init__(self) -> None:
        self.store = AgentStore()

    async def record(
        self,
        run_id: UUID,
        step: str,
        *,
        status: str = "completed",
        payload: dict[str, object] | None = None,
    ) -> None:
        await self.store.create_trace(
            run_id=run_id,
            step=step,
            status=status,
            payload=payload or {},
        )

    async def list_for_run(self, run_id: UUID) -> list[dict[str, object]]:
        return await self.store.list_run_traces(run_id)
