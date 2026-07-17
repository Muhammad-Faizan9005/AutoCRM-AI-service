from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.core.idempotency import build_idempotency_key
from app.schemas.events import AgentEventIn
from app.services.autocrm_client import AutoCRMClient


@dataclass
class RunContext:
    run_id: UUID
    backend_run_id: UUID
    trigger_type: str
    entity_id: UUID
    entity_type: str
    idempotency_key: str
    correlation_id: str = ""


class RunManager:
    def __init__(self) -> None:
        self.client = AutoCRMClient()

    async def start_run(self, payload: AgentEventIn) -> RunContext | None:
        window_bucket = self._window_bucket(payload)
        key = build_idempotency_key(payload.event_type, payload.entity_id, window_bucket)
        run_id = uuid5(NAMESPACE_URL, f"autocrm-ai-run:{key}")
        run = await self.client.create_run(
            external_run_id=run_id,
            trigger_type=payload.event_type,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            event_payload=payload.model_dump(mode="json"),
        )
        backend_run_id = UUID(str(run.get("id") or run_id))
        if str(run.get("status") or "").lower() in {"completed", "failed", "cancelled"}:
            return None

        return RunContext(
            run_id=run_id,
            backend_run_id=backend_run_id,
            trigger_type=payload.event_type,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            idempotency_key=key,
        )

    async def complete_run(
        self,
        run_id: UUID,
        status: str,
        summary: str | None = None,
        failure_cause: str | None = None,
        failure_detail: str | None = None,
    ) -> None:
        await self.client.complete_run(
            run_id,
            status=status,
            summary=summary,
            failure_cause=failure_cause,
            failure_detail=failure_detail,
        )

    def _window_bucket(self, payload: AgentEventIn) -> str:
        metadata = payload.metadata or {}
        event_id = metadata.get("event_id")
        recording_id = metadata.get("recording_id")
        if event_id:
            return f"event:{event_id}"
        if recording_id:
            return f"recording:{recording_id}"
        if payload.event_type == "daily_summary":
            return datetime.utcnow().strftime("%Y-%m-%d")
        return datetime.utcnow().strftime("%Y-%m-%dT%H")
