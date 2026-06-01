from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class MeetingIntelWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            summary = ""
            try:
                summary = await llm.generate(workflow="meeting_intel", context=str(context), model_tier="large")
            except Exception:
                summary = ""
            if not summary:
                summary = "Review meeting notes and create action items."
            return AgentAction(
                action_type="create_task",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="Meeting action items",
                data={"title": "Review meeting action items", "description": summary, "context": context},
                requires_approval=True,
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
