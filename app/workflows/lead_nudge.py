from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class LeadNudgeWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            prompt = (
                "Draft a short follow-up task title and description for a sales rep. "
                "Keep it under 2 sentences.\n\n"
                f"Context: {context}"
            )
            content = ""
            try:
                content = await llm.generate(prompt=prompt, model_tier="small")
            except Exception:
                content = ""
            if not content:
                content = "Follow up with the lead and capture next steps."
            return AgentAction(
                action_type="create_task",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="No recent activity",
                data={"title": "Follow up with lead", "description": content, "context": context},
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
