from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.workflows.base import BaseWorkflow
from app.workflows.graph_runner import GraphRunner


ACTION_CUES = (
    "action item",
    "follow up",
    "send ",
    "email ",
    "call back",
    "schedule",
    "book",
    "prepare",
    "share",
    "update",
    "create",
    "assign",
    "review",
    "proposal",
    "quote",
    "contract",
    "invoice",
    "demo",
    "deadline",
    "due",
    "by tomorrow",
    "by monday",
    "next week",
    "need to",
    "we should",
    "i will",
    "i'll",
    "can you",
    "please",
)

NO_ACTION_RESPONSES = {
    "no_action_items",
    "no action items",
    "none",
    "no actionable items",
    "no actions",
}


def _has_actionable_content(transcript: str) -> bool:
    normalized = f" {transcript.lower()} "
    if len(normalized.strip()) < 40:
        return False
    return any(cue in normalized for cue in ACTION_CUES)


def _clean_summary(value: str) -> str:
    cleaned = (value or "").strip().strip("` ")
    if cleaned.lower().startswith("summary:"):
        cleaned = cleaned.split(":", 1)[1].strip()
    return cleaned


class MeetingIntelWorkflow(BaseWorkflow):
    async def run(self, payload: AgentEventIn, run_context: RunContext) -> None:
        runner = GraphRunner()
        llm = LLMService()

        async def make_action(event: AgentEventIn, context: dict[str, object]) -> AgentAction | None:
            metadata = event.metadata or {}
            transcript = str(metadata.get("transcript") or "").strip()
            enriched_context = {
                **context,
                "meeting_metadata": metadata,
                "transcript": transcript,
            }

            if not _has_actionable_content(transcript):
                return None

            prompt = (
                "Extract only concrete follow-up action items from this meeting transcript. "
                "If the transcript contains only greetings, mic tests, small talk, or no explicit next steps, "
                "return exactly NO_ACTION_ITEMS. If actions exist, return a concise task description, "
                "including owner/deadline only when clearly stated. Do not invent tasks.\n\n"
                f"Transcript:\n{transcript}"
            )

            try:
                summary = await llm.generate(
                    prompt=prompt,
                    workflow="meeting_intel",
                    context=str(enriched_context),
                    model_tier="large",
                )
            except Exception:
                summary = ""

            summary = _clean_summary(summary)
            if not summary or summary.lower() in NO_ACTION_RESPONSES:
                return None

            return AgentAction(
                action_type="create_task",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="Meeting action items extracted from meeting transcript",
                data={
                    "title": "Meeting follow-up action item",
                    "description": summary,
                    "context": enriched_context,
                },
                requires_approval=True,
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
