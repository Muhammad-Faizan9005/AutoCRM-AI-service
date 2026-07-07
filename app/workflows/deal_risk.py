from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.planner_service import PlannerService
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


def _compact_context(context: dict[str, object]) -> dict[str, object]:
    snapshot = context.get("entity_snapshot") if isinstance(context, dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    docs = context.get("rag_docs") if isinstance(context, dict) else []
    doc_summaries = []
    for doc in docs if isinstance(docs, list) else []:
        if not isinstance(doc, dict):
            continue
        content = str(doc.get("content") or "")
        doc_summaries.append(
            {
                "source": doc.get("source"),
                "source_id": doc.get("source_id"),
                "content": content[:280],
            }
        )
        if len(doc_summaries) >= 3:
            break
    return {
        "deal_stage": snapshot.get("stage"),
        "deal_status": snapshot.get("status"),
        "value": snapshot.get("value"),
        "currency": snapshot.get("currency"),
        "expected_close_at": snapshot.get("expected_close_at"),
        "recent_context": doc_summaries,
    }


def _bounded_text(value: object, fallback: str, limit: int) -> str:
    text = str(value or "").strip() or fallback
    text = " ".join(text.split())
    return text[:limit].rstrip()


class DealRiskWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()
        planner = PlannerService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            plan = await planner.plan_action(event, context)
            message = ""
            try:
                message = await llm.generate(workflow="deal_risk", context=str(context), model_tier="large")
            except Exception:
                message = ""
            if not message:
                message = "Deal appears at risk. Review stage progress and next steps."
            recipient_id = plan.recipient_id or event.actor_id or ""
            title = _bounded_text(plan.title, "Deal risk alert", 120)
            reason = _bounded_text(plan.reason, "Deal risk detected", 500)
            return AgentAction(
                action_type="create_alert",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason=reason,
                data={
                    "title": title,
                    "message": _bounded_text(message, "Deal appears at risk. Review stage progress and next steps.", 260),
                    "recipient_id": recipient_id,
                    "context": _compact_context(context),
                },
                requires_approval=False,
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
