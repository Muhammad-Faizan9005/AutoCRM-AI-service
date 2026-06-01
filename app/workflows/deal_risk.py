from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


class DealRiskWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            message = ""
            try:
                message = await llm.generate(workflow="deal_risk", context=str(context), model_tier="large")
            except Exception:
                message = ""
            if not message:
                message = "Deal appears at risk. Review stage progress and next steps."
            recipient_id = event.actor_id or ""
            return AgentAction(
                action_type="create_alert",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="Deal risk detected",
                data={
                    "title": "Deal risk alert",
                    "message": message,
                    "recipient_id": recipient_id,
                    "context": context,
                },
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
