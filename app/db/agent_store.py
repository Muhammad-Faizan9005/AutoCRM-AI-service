from __future__ import annotations

from datetime import datetime
import json
from uuid import UUID

try:
    import asyncpg  # noqa: F401
except ImportError:  # pragma: no cover
    asyncpg = None

from app.db.pool import get_pool


class AgentStore:
    def _serialize_payload(self, payload: dict[str, object]) -> str:
        return json.dumps(payload, default=str)

    async def create_run(
        self,
        *,
        run_id: UUID,
        trigger_type: str,
        entity_id: UUID,
        entity_type: str,
        idempotency_key: str,
        status: str = "running",
    ) -> None:
        query = (
            "INSERT INTO ai_runs (id, trigger_type, entity_id, entity_type, status, idempotency_key) "
            "VALUES ($1, $2, $3::uuid, $4, $5, $6)"
        )
        await get_pool().execute(
            query,
            run_id,
            trigger_type,
            entity_id,
            entity_type,
            status,
            idempotency_key,
        )

    async def complete_run(
        self,
        *,
        run_id: UUID,
        status: str,
        summary: str | None = None,
        failure_cause: str | None = None,
        failure_detail: str | None = None,
    ) -> None:
        query = (
            "UPDATE ai_runs SET status=$1, summary=$2, failure_cause=$3, failure_detail=$4, finished_at=$5 "
            "WHERE id=$6"
        )
        await get_pool().execute(
            query,
            status,
            summary,
            failure_cause,
            failure_detail,
            datetime.utcnow(),
            run_id,
        )

    async def create_action(
        self,
        *,
        action_id: UUID,
        run_id: UUID,
        action_type: str,
        entity_type: str,
        entity_id: UUID,
        reason: str,
        payload: dict[str, object],
        idempotency_key: str | None,
        approval_status: str,
    ) -> None:
        query = (
            "INSERT INTO ai_actions (id, run_id, action_type, entity_type, entity_id, reason, payload, idempotency_key, approval_status) "
            "VALUES ($1, $2, $3, $4, $5::uuid, $6, $7::jsonb, $8, $9)"
        )
        await get_pool().execute(
            query,
            action_id,
            run_id,
            action_type,
            entity_type,
            entity_id,
            reason,
            self._serialize_payload(payload),
            idempotency_key,
            approval_status,
        )

    async def create_trace(
        self,
        *,
        run_id: UUID,
        step: str,
        status: str,
        payload: dict[str, object],
    ) -> None:
        query = (
            "INSERT INTO ai_run_traces (run_id, step, status, payload) "
            "VALUES ($1, $2, $3, $4::jsonb)"
        )
        await get_pool().execute(query, run_id, step, status, self._serialize_payload(payload))

    async def list_run_traces(self, run_id: UUID) -> list[dict[str, object]]:
        query = (
            "SELECT step, status, payload, created_at "
            "FROM ai_run_traces WHERE run_id=$1 "
            "ORDER BY created_at ASC"
        )
        rows = await get_pool().fetch(query, run_id)
        return [dict(row) for row in rows]

    async def create_approval_request(
        self,
        *,
        request_id: UUID,
        agent_action_id: UUID,
        requested_by: str,
        approver_id: UUID | None,
        reason: str,
        expires_at: datetime | None,
        fallback_policy: str = "skip",
    ) -> None:
        query = (
            "INSERT INTO ai_approval_requests (id, agent_action_id, requested_by, approver_id, reason, expires_at, fallback_policy) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)"
        )
        await get_pool().execute(
            query,
            request_id,
            agent_action_id,
            requested_by,
            approver_id,
            reason,
            expires_at,
            fallback_policy,
        )

    async def run_exists(self, idempotency_key: str) -> bool:
        query = "SELECT 1 FROM ai_runs WHERE idempotency_key=$1 LIMIT 1"
        row = await get_pool().fetchrow(query, idempotency_key)
        return row is not None

    async def list_recent_entity_actions(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        query = (
            "SELECT action_type, reason, payload, approval_status, created_at "
            "FROM ai_actions "
            "WHERE entity_id=$1::uuid AND entity_type=$2 "
            "ORDER BY created_at DESC LIMIT $3"
        )
        rows = await get_pool().fetch(query, entity_id, entity_type, limit)
        return [dict(row) for row in rows]
