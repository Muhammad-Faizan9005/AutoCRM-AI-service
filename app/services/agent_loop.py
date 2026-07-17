from __future__ import annotations

import logging
from uuid import UUID

from app.core.metrics import content_generation_failures_total
from app.core.retry import classify_failure
from app.schemas.actions import AgentAction
from app.schemas.events import AgentEventIn
from app.schemas.planner import PlannedAction
from app.services.action_manager import ActionManager
from app.services.context_service import ContextService
from app.services.llm_service import LLMService
from app.services.planner_service import PlannerService
from app.services.run_manager import RunContext
from app.services.run_trace_service import RunTraceService
from app.services.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentLoop:
    SUPPORTED_EVENTS = {"stale_lead", "deal_risk", "daily_summary"}

    def __init__(self) -> None:
        self.context_service = ContextService()
        self.planner = PlannerService()
        self.llm = LLMService()
        self.action_manager = ActionManager()
        self.trace = RunTraceService()
        self.tools = ToolRegistry()

    def supports(self, payload: AgentEventIn) -> bool:
        return payload.event_type in self.SUPPORTED_EVENTS

    async def run(self, payload: AgentEventIn, run_context: RunContext) -> UUID:
        await self.trace.record(
            run_context.backend_run_id,
            "event_received",
            payload=payload.model_dump(mode="json"),
        )

        await self.trace.record(
            run_context.backend_run_id,
            "tool_registry_loaded",
            payload={"tools": self.tools.list_tools()},
        )

        context = await self.context_service.build_context(
            payload.entity_id,
            payload.entity_type,
            event_type=payload.event_type,
            metadata=payload.metadata or {},
        )
        await self.trace.record(
            run_context.backend_run_id,
            "context_built",
            payload={
                "context": context,
                "read_tools_used": self._read_tools_for(payload.entity_type),
            },
        )

        plan = await self.planner.plan_action(payload, context)
        await self.trace.record(
            run_context.backend_run_id,
            "plan_made",
            payload={"plan": plan.model_dump(mode="json")},
        )

        action = await self._build_action(payload, context, plan)
        await self.trace.record(
            run_context.backend_run_id,
            "tool_chosen",
            payload={
                "tool": plan.selected_tool,
                "requires_approval": action.requires_approval,
                "reason": action.reason,
            },
        )

        action_id = await self.action_manager.create_action(run_context.run_id, action)
        await self.trace.record(
            run_context.backend_run_id,
            "action_executed",
            payload={
                "action_id": str(action_id),
                "action_type": action.action_type,
                "approval_status": action.approval_status,
            },
        )
        return action_id

    async def _build_action(
        self,
        payload: AgentEventIn,
        context: dict[str, object],
        plan: PlannedAction,
    ) -> AgentAction:
        content = await self._generate_content(payload, context, plan)
        action_context = self._compact_action_context(context)
        data: dict[str, object]

        if plan.action_type == "create_alert":
            data = {
                "title": plan.title or "Deal risk alert",
                "message": plan.message or content or "Review this CRM item.",
                "recipient_id": plan.recipient_id or payload.actor_id or "",
                "context": action_context,
            }
        elif plan.action_type == "create_note":
            data = {
                "title": plan.title or "Agent note",
                "content": plan.description or content or "Agent note created from CRM event.",
                "context": action_context,
            }
        else:
            data = {
                "title": plan.title or "Follow up",
                "description": plan.description or content or "Follow up and capture next steps.",
                "context": action_context,
            }

        return AgentAction(
            action_type=plan.action_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            reason=plan.reason,
            data=data,
            requires_approval=plan.requires_approval,
        )

    async def _generate_content(
        self,
        payload: AgentEventIn,
        context: dict[str, object],
        plan: PlannedAction,
    ) -> str:
        workflow = {
            "stale_lead": "lead_nudge",
            "deal_risk": "deal_risk",
            "daily_summary": "daily_summary",
        }.get(payload.event_type)
        if workflow is None:
            return ""
        try:
            return await self.llm.generate(
                workflow=workflow,
                context=str({"context": context, "plan": plan.model_dump(mode="json")}),
                model_tier="large" if payload.event_type == "deal_risk" else "small",
                prompt="",
            )
        except Exception as exc:
            # Increment metrics and let the exception propagate to the
            # orchestrator's _execute_agent_loop, which marks the run failed.
            category = classify_failure(exc)
            content_generation_failures_total.inc(category=category)
            logger.exception(
                "content_generation_failed category=%s workflow=%s",
                category,
                workflow,
            )
            raise

    def _read_tools_for(self, entity_type: str) -> list[str]:
        normalized = entity_type.strip().lower()
        if normalized == "lead":
            return ["fetch_lead", "entity_memory", "rag_retrieve"]
        if normalized == "deal":
            return ["fetch_deal", "entity_memory", "rag_retrieve"]
        if normalized == "user":
            return ["fetch_user", "entity_memory", "rag_retrieve"]
        return ["entity_memory", "rag_retrieve"]

    def _compact_action_context(self, context: dict[str, object]) -> dict[str, object]:
        snapshot = context.get("entity_snapshot")
        if isinstance(snapshot, dict):
            snapshot = {
                key: value
                for key, value in snapshot.items()
                if key in {"id", "name", "title", "status", "stage", "score", "owner_id", "updated_at"} and value is not None
            }
        memory = context.get("entity_memory")
        if isinstance(memory, list):
            memory = memory[:3]
        rag_docs = context.get("rag_docs")
        if isinstance(rag_docs, list):
            rag_docs = [
                {
                    "source": doc.get("source"),
                    "score": doc.get("score"),
                    "metadata": doc.get("metadata"),
                }
                for doc in rag_docs[:3]
                if isinstance(doc, dict)
            ]
        return {
            "entity_id": context.get("entity_id"),
            "entity_type": context.get("entity_type"),
            "entity_snapshot": snapshot or {},
            "entity_memory": memory or [],
            "rag_refs": rag_docs or [],
        }
