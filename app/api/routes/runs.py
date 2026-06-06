from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.schemas.runs import AgentRunStatus, AgentRunTrace
from app.services.run_trace_service import RunTraceService


router = APIRouter()


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> AgentRunStatus:
    return AgentRunStatus(run_id=run_id, status="pending", summary=None)


@router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: UUID) -> list[AgentRunTrace]:
    trace = await RunTraceService().list_for_run(run_id)
    return [AgentRunTrace.model_validate(item) for item in trace]
