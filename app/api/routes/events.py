from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.dependencies import require_webhook_token
from app.schemas.events import AgentEventIn
from app.services.agent_orchestrator import AgentOrchestrator


router = APIRouter()


@router.post("/events", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_webhook_token)])
async def ingest_event(payload: AgentEventIn) -> dict[str, str]:
    orchestrator = AgentOrchestrator()
    await orchestrator.handle_event(payload)
    return {"status": "accepted"}
