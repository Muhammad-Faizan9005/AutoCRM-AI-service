from __future__ import annotations

import logging

from app.schemas.events import AgentEventIn
from app.services.run_manager import RunManager
from app.services.workflow_router import WorkflowRouter


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self) -> None:
        self.router = WorkflowRouter()
        self.run_manager = RunManager()

    async def handle_event(self, payload: AgentEventIn) -> None:
        workflow = self.router.resolve(payload)
        if workflow is None:
            logger.info("No workflow for event_type=%s", payload.event_type)
            return
        run_context = await self.run_manager.start_run(payload)
        if run_context is None:
            logger.info("Skipped duplicate event for entity_id=%s", payload.entity_id)
            return
        try:
            await workflow.run(payload, run_context)
            await self.run_manager.complete_run(run_context.run_id, status="completed")
        except Exception as exc:
            await self.run_manager.complete_run(
                run_context.run_id,
                status="failed",
                failure_cause="WORKFLOW_ERROR",
                failure_detail=str(exc),
            )
            raise
