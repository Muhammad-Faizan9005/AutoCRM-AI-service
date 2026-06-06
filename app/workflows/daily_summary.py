from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.planner_service import PlannerService
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class DailySummaryWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()
        planner = PlannerService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            plan = await planner.plan_action(event, context)
            summary = ""
            try:
                summary = await llm.generate(workflow="daily_summary", context=str(context), model_tier="small")
            except Exception:
                summary = ""
            if not summary:
                summary = "Daily summary is not available yet. Check leads and tasks for updates."
            return AgentAction(
                action_type=plan.action_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason=plan.reason,
                data={"title": plan.title or "Daily summary", "content": summary, "context": context},
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
