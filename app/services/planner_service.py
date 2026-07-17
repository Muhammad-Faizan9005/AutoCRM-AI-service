from __future__ import annotations

import json
import logging

from app.core.metrics import planner_failures_total
from app.core.retry import classify_failure
from app.schemas.events import AgentEventIn
from app.schemas.planner import PlannedAction
from app.services.action_policy import validate_planned_action
from app.services.llm_service import LLMService
from app.prompts import load_prompt

logger = logging.getLogger(__name__)


class PlannerService:
    def __init__(self) -> None:
        self.llm = LLMService()

    async def plan_action(self, payload: AgentEventIn, context: dict[str, object]) -> PlannedAction:
        fallback = self._fallback_plan(payload)

        planner_context = (
            "Return ONLY JSON with keys: event_meaning, needs_more_context, selected_tool, "
            "action_type, reason, title, description, message, recipient_id, requires_approval. "
            "Choose selected_tool/action_type from create_task, create_note, create_alert. "
            "Use requires_approval=true for AI-created tasks, outbound messages, stage changes, or uncertain/high-risk actions. "
            "Alerts are informational and should not require approval unless explicitly asked.\n\n"
            f"Event type: {payload.event_type}\n"
            f"Entity type: {payload.entity_type}\n"
            f"Actor id: {payload.actor_id}\n"
            f"Metadata: {payload.metadata or {}}\n"
            f"Context: {context}"
        )
        prompt = load_prompt("planner", planner_context)

        try:
            raw = await self.llm.generate(prompt=prompt, model_tier="small", json_mode=True)
            data = json.loads(raw)
            plan = PlannedAction.model_validate(data)
            return self._normalize_plan(payload, plan)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            # Parseable-but-malformed JSON or validation error — use fallback.
            logger.warning(
                "planner_fallback_used reason=parse_error error=%s",
                exc,
            )
            planner_failures_total.inc(category="INVALID_REQUEST")
            return self._normalize_plan(payload, fallback)
        # Transport / circuit / retry-exhausted errors are NOT caught here —
        # they propagate to the orchestrator's _execute_agent_loop try/except
        # which marks the run as failed with a structured failure category.

    def _normalize_plan(self, payload: AgentEventIn, plan: PlannedAction) -> PlannedAction:
        if plan.selected_tool is None:
            plan.selected_tool = plan.action_type
        if plan.action_type == "create_alert" and not plan.recipient_id:
            plan.recipient_id = payload.actor_id or ""
        if not plan.reason:
            plan.reason = self._fallback_plan(payload).reason
        if not plan.event_meaning:
            plan.event_meaning = self._fallback_plan(payload).event_meaning

        # Enforce action policy (allowlist, approval, recipient sanitisation)
        plan = validate_planned_action(plan, payload)

        return plan

    def _fallback_plan(self, payload: AgentEventIn) -> PlannedAction:
        event_type = payload.event_type.strip().lower()

        if event_type == "daily_summary":
            return PlannedAction(
                event_meaning="A daily CRM summary should be prepared for the user.",
                selected_tool="create_note",
                action_type="create_note",
                reason="Daily summary",
                title="Daily summary",
                description="",
            )

        if event_type == "deal_risk":
            return PlannedAction(
                event_meaning="A deal appears risky and needs human attention.",
                selected_tool="create_alert",
                action_type="create_alert",
                reason="Deal risk detected",
                title="Deal risk alert",
                message="Deal appears at risk. Review stage progress and next steps.",
                recipient_id=payload.actor_id or "",
                requires_approval=False,
            )

        return PlannedAction(
            event_meaning="A lead needs proactive follow-up.",
            selected_tool="create_task",
            action_type="create_task",
            reason="No recent activity",
            title="Follow up with lead",
            description="Follow up with the lead and capture next steps.",
            requires_approval=True,
        )
