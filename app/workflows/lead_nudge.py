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
        "lead_name": snapshot.get("name"),
        "lead_email": snapshot.get("email"),
        "company": snapshot.get("company"),
        "status": snapshot.get("status"),
        "recent_context": doc_summaries,
    }


def _bounded_text(value: object, fallback: str, limit: int) -> str:
    text = str(value or "").strip() or fallback
    text = " ".join(text.split())
    return text[:limit].rstrip()


class LeadNudgeWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()
        planner = PlannerService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction:
            plan = await planner.plan_action(event, context)
            content = ""
            prompt = (
                "Write one compact CRM follow-up recommendation for this lead. "
                "Return plain text only, no markdown, no headings, no bullets. "
                "Use at most two short sentences and 45 words. "
                "Include the specific follow-up reason and the next detail to capture. "
                "Do not include analysis, implementation details, or a full report.\n\n"
                f"Lead event: {event.event_type}\nContext: {context}"
            )
            try:
                content = await llm.generate(prompt=prompt, workflow=None, context="", model_tier="small")
            except Exception:
                content = ""
            if not content:
                content = f"Follow up with this lead because {plan.reason.lower()}. Capture the next step, timeline, and decision maker."
            compact_context = _compact_context(context)
            title = _bounded_text(plan.title, "Follow up with lead", 120)
            reason = _bounded_text(plan.reason, "No recent activity", 500)
            data: dict[str, object] = {
                "title": title,
                "description": _bounded_text(content, "Follow up with the lead and capture next steps.", 280),
                "context": compact_context,
            }
            if event.actor_id:
                data["assigned_to"] = event.actor_id
            return AgentAction(
                action_type="create_task",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason=reason,
                data=data,
                requires_approval=True,
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
