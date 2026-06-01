from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from app.core.idempotency import build_idempotency_key
from app.db.agent_store import AgentStore
from app.schemas.events import AgentEventIn


@dataclass
class RunContext:
    run_id: UUID
    trigger_type: str
    entity_id: UUID
    entity_type: str
    idempotency_key: str


class RunManager:
    def __init__(self) -> None:
        self.store = AgentStore()

    async def start_run(self, payload: AgentEventIn) -> RunContext | None:
        window_bucket = self._window_bucket(payload)
        key = build_idempotency_key(payload.event_type, payload.entity_id, window_bucket)
        if await self.store.run_exists(key):
            return None

        run_id = uuid4()
        try:
            await self.store.create_run(
                run_id=run_id,
                trigger_type=payload.event_type,
                entity_id=payload.entity_id,
                entity_type=payload.entity_type,
                idempotency_key=key,
            )
        except asyncpg.UniqueViolationError:
            return None

        return RunContext(
            run_id=run_id,
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
        await self.store.complete_run(
            run_id=run_id,
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
