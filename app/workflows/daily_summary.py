from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class DailySummaryWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()

        def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            return AgentAction(
                action_type="create_note",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="Daily summary",
                data={"title": "Daily summary", "content": "Summary placeholder", "context": context},
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
