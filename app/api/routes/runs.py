from __future__ import annotations

from fastapi import APIRouter

from app.schemas.runs import AgentRunStatus


router = APIRouter()


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> AgentRunStatus:
    return AgentRunStatus(run_id=run_id, status="pending", summary=None)
