from __future__ import annotations

from uuid import UUID

from app.services.autocrm_client import AutoCRMClient


class RunTraceService:
    def __init__(self) -> None:
        self.client = AutoCRMClient()

    async def record(
        self,
        run_id: UUID,
        step: str,
        *,
        status: str = "completed",
        payload: dict[str, object] | None = None,
    ) -> None:
        await self.client.create_run_trace(
            run_id,
            step=step,
            status=status,
            payload=payload or {},
        )

    async def list_for_run(self, run_id: UUID) -> list[dict[str, object]]:
        return await self.client.list_run_traces(run_id)
