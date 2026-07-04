from __future__ import annotations

import json
from datetime import datetime, timezone

from app.schemas.events import AgentEventIn
from app.schemas.actions import AgentAction
from app.services.run_manager import RunContext
from app.services.llm_service import LLMService
from app.services.content_formatter import format_ai_text
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
    return format_ai_text(cleaned, max_length=1200)


def _parse_action_payload(raw: str) -> dict[str, object] | None:
    cleaned = _clean_summary(raw)
    if not cleaned or cleaned.lower() in NO_ACTION_RESPONSES:
        return None
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("` ")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "title": "Meeting follow-up",
            "description": cleaned.splitlines()[0][:220],
            "note_content": cleaned,
            "due_at": None,
            "priority": "medium",
        }
    if not isinstance(parsed, dict):
        return None
    title = str(parsed.get("title") or "Meeting follow-up").strip()[:120]
    description = str(parsed.get("task_description") or parsed.get("description") or title).strip()
    note_content = str(parsed.get("note_content") or parsed.get("details") or "").strip()
    due_at = parsed.get("due_at")
    priority = str(parsed.get("priority") or "medium").strip().lower()
    if priority not in {"low", "medium", "high"}:
        priority = "medium"
    return {
        "title": title,
        "description": description[:240],
        "note_content": note_content,
        "due_at": str(due_at).strip() if due_at else None,
        "priority": priority,
    }


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
                "Extract only one concrete CRM follow-up task from this meeting transcript. "
                "If the transcript contains only greetings, mic tests, small talk, or no explicit next steps, "
                "return exactly NO_ACTION_ITEMS. Do not invent tasks.\n\n"
                "Return valid JSON only with these keys:\n"
                "- title: short imperative task title, max 10 words.\n"
                "- task_description: one concise sentence, max 25 words. No bullet lists.\n"
                "- due_at: ISO 8601 datetime when a deadline/date/time is clearly stated, otherwise null. "
                "Use timezone +05:00 for relative/local meeting times.\n"
                "- priority: low, medium, or high.\n"
                "- note_content: extra customer details, quantities, product names, transcript context, and longer notes. "
                "Put verbose details here, not in task_description.\n\n"
                f"Current date: {datetime.now(timezone.utc).date().isoformat()}\n\n"
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

            action_payload = _parse_action_payload(summary)
            if not action_payload:
                return None

            actor_id = str(event.actor_id or metadata.get("actor_id") or "").strip() or None
            return AgentAction(
                action_type="create_task",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                reason="Meeting action items extracted from meeting transcript",
                data={
                    "title": action_payload["title"],
                    "description": action_payload["description"],
                    "due_at": action_payload.get("due_at"),
                    "priority": action_payload.get("priority") or "medium",
                    "assigned_to": actor_id,
                    "actor_id": actor_id,
                    "note_content": action_payload.get("note_content"),
                    "context": enriched_context,
                },
                requires_approval=True,
            )

        graph = runner.build(make_action)
        await graph.ainvoke({"payload": payload, "run_context": run_context, "context": {}, "action": None})
