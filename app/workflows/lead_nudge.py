from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.planner_service import PlannerService
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class LeadNudgeWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()
        planner = PlannerService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            plan = await planner.plan_action(event, context)
            content = ""
            prompt = (
                "Write a personalized CRM follow-up suggestion for this lead. "
                "Use the provided CRM context and mention the specific reason for the follow-up. "
                "Avoid generic advice. If context is thin, say what information should be captured next.\n\n"
                f"Lead event: {event.event_type}\nContext: {context}"
            )
            try:
                content = await llm.generate(prompt=prompt, workflow=None, context="", model_tier="small")
            except Exception:
                content = ""
            if not content:
                content = f"Follow up with this lead because {plan.reason.lower()}. Capture the next step, timeline, and decision maker."
            return AgentAction(
                action_type=plan.action_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason=plan.reason,
                data={"title": plan.title or "Follow up with lead", "description": content, "context": context},
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
