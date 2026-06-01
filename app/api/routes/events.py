from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.events import AgentEventIn
from app.services.agent_orchestrator import AgentOrchestrator


router = APIRouter()


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(payload: AgentEventIn) -> dict[str, str]:
    orchestrator = AgentOrchestrator()
    await orchestrator.handle_event(payload)
    return {"status": "accepted"}
