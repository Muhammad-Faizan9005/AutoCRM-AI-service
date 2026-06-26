from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.schemas.runs import AgentRunStatus, AgentRunTrace
from app.services.autocrm_client import AutoCRMClient


router = APIRouter()


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> AgentRunStatus:
    run = await AutoCRMClient().get_run(run_id)
    return AgentRunStatus(
        run_id=str(run.get("id") or run_id),
        status=str(run.get("status") or "unknown"),
        summary=run.get("summary"),
    )


@router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: UUID) -> list[AgentRunTrace]:
    trace = await AutoCRMClient().list_run_traces(run_id)
    return [AgentRunTrace.model_validate(item) for item in trace]
