from __future__ import annotations

import logging
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.config import settings
from app.core.correlation import new_correlation_id, set_correlation_id, set_run_id
from app.core.retry import classify_failure
from app.schemas.events import AgentEventIn
from app.services.agent_loop import AgentLoop
from app.services.autocrm_client import AutoCRMClient
from app.services.run_manager import RunContext, RunManager
from app.services.workflow_router import WorkflowRouter


logger = logging.getLogger(__name__)

OrchestrationOutcome = Literal[
    "accepted",
    "unsupported",
    "duplicate",
    "executed",
    "failed",
    "completed",
]


class OrchestrationState(TypedDict, total=False):
    payload: AgentEventIn
    agent_type: str
    run_context: RunContext
    outcome: OrchestrationOutcome
    failure_cause: str
    failure_detail: str


class AgentOrchestrator:
    """
    LangGraph control plane for one inbound event.

    The orchestrator owns lifecycle decisions: event interpretation, run
    creation/idempotency, success/failure transitions, and terminal states.
    The AgentLoop owns the inner agent work: context, planning, tool choice,
    execution, approvals, and trace details.
    """

    AGENT_EVENT_MAP = {
        "stale_lead": "lead_assistant",
        "deal_risk": "deal_risk_watcher",
        "daily_summary": "daily_summary_assistant",
        "task_auto": "action_manager_agent",
        "meeting_complete": "meeting_agent",
        "task_deadline_watch": "task_deadline_watcher",
        "frontdesk_message": "frontdesk_agent",
    }

    AGENT_SETTING_ALIASES = {
        "action_manager_agent": {"action_manager_agent", "action_manager", "task_auto"},
        "lead_assistant": {"lead_assistant", "stale_lead", "lead_nudge"},
        "deal_risk_watcher": {"deal_risk_watcher", "deal_risk"},
        "daily_summary_assistant": {"daily_summary_assistant", "daily_summary", "summary_assistant"},
        "meeting_agent": {"meeting_agent", "meeting_assistant", "meeting_complete", "meeting_intel"},
        "task_deadline_watcher": {"task_deadline_watcher", "task_deadline_watch", "deadline_watch"},
        "frontdesk_agent": {"frontdesk_agent", "frontdesk", "frontdesk_message"},
    }

    def __init__(self) -> None:
        self.loop = AgentLoop()
        self.workflow_router = WorkflowRouter()
        self.run_manager = RunManager()
        self.client = AutoCRMClient()
        self.graph = self._build_graph()

    async def handle_event(self, payload: AgentEventIn) -> None:
        # Create and set a correlation ID at event ingress
        correlation_id = new_correlation_id()
        set_correlation_id(correlation_id)
        logger.info(
            "event_ingress event_type=%s entity_id=%s correlation_id=%s",
            payload.event_type,
            payload.entity_id,
            correlation_id,
        )
        await self.graph.ainvoke({"payload": payload})

    def _build_graph(self):
        graph = StateGraph(OrchestrationState)
        graph.add_node("interpret_event", self._interpret_event)
        graph.add_node("start_run", self._start_run)
        graph.add_node("execute_agent_loop", self._execute_agent_loop)
        graph.add_node("complete_run", self._complete_run)
        graph.add_node("fail_run", self._fail_run)

        graph.set_entry_point("interpret_event")
        graph.add_conditional_edges(
            "interpret_event",
            self._route_after_interpretation,
            {
                "start_run": "start_run",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "start_run",
            self._route_after_start,
            {
                "execute_agent_loop": "execute_agent_loop",
                "end": END,
            },
        )
        graph.add_conditional_edges(
            "execute_agent_loop",
            self._route_after_execution,
            {
                "complete_run": "complete_run",
                "fail_run": "fail_run",
            },
        )
        graph.add_edge("complete_run", END)
        graph.add_edge("fail_run", END)
        return graph.compile()

    async def _interpret_event(self, state: OrchestrationState) -> OrchestrationState:
        payload = state["payload"]
        agent_type = self.AGENT_EVENT_MAP.get(payload.event_type)
        if agent_type is None:
            logger.info("No agent registered for event_type=%s", payload.event_type)
            state["outcome"] = "unsupported"
            return state
        if not await self._agent_enabled(agent_type):
            logger.info("Agent disabled for event_type=%s agent_type=%s", payload.event_type, agent_type)
            state["outcome"] = "unsupported"
            return state

        state["agent_type"] = agent_type
        state["outcome"] = "accepted"
        return state

    async def _start_run(self, state: OrchestrationState) -> OrchestrationState:
        run_context = await self.run_manager.start_run(state["payload"])
        if run_context is None:
            logger.info("Skipped duplicate event for entity_id=%s", state["payload"].entity_id)
            state["outcome"] = "duplicate"
            return state

        # Set run_id in context vars for logging
        set_run_id(str(run_context.backend_run_id))

        state["run_context"] = run_context
        state["outcome"] = "accepted"
        return state

    async def _execute_agent_loop(self, state: OrchestrationState) -> OrchestrationState:
        try:
            payload = state["payload"]
            workflow = self.workflow_router.resolve(payload)
            if workflow is not None:
                await workflow.run(payload, state["run_context"])
            else:
                await self.loop.run(payload, state["run_context"])
            state["outcome"] = "executed"
        except Exception as exc:
            state["outcome"] = "failed"
            # Use structured failure category from the central classifier
            state["failure_cause"] = classify_failure(exc)
            # Gate failure detail behind dev mode
            if settings.is_dev:
                state["failure_detail"] = str(exc)
            else:
                state["failure_detail"] = "An internal error occurred. Check service logs for details."
            # Always log the full error with correlation context
            logger.exception(
                "agent_loop_failed failure_cause=%s",
                state["failure_cause"],
            )
            run_context = state.get("run_context")
            if run_context is not None:
                try:
                    await self.client.create_run_trace(
                        run_id=run_context.backend_run_id,
                        step="agent_loop",
                        status="failed",
                        payload={
                            "error": state["failure_detail"],
                            "failure_cause": state["failure_cause"],
                        },
                    )
                except Exception:
                    logger.exception("failed_to_record_agent_loop_trace")
        return state

    async def _complete_run(self, state: OrchestrationState) -> OrchestrationState:
        await self.run_manager.complete_run(
            state["run_context"].backend_run_id,
            status="completed",
            summary=f"{state['agent_type']} completed",
        )
        state["outcome"] = "completed"
        return state

    async def _fail_run(self, state: OrchestrationState) -> OrchestrationState:
        await self.run_manager.complete_run(
            state["run_context"].backend_run_id,
            status="failed",
            failure_cause=state.get("failure_cause", "AGENT_ORCHESTRATION_ERROR"),
            failure_detail=state.get("failure_detail"),
        )
        return state

    def _route_after_interpretation(self, state: OrchestrationState) -> str:
        if state["outcome"] == "accepted":
            return "start_run"
        return "end"

    def _route_after_start(self, state: OrchestrationState) -> str:
        if state["outcome"] == "duplicate":
            return "end"
        return "execute_agent_loop"

    def _route_after_execution(self, state: OrchestrationState) -> str:
        if state["outcome"] == "failed":
            return "fail_run"
        return "complete_run"

    async def _agent_enabled(self, agent_type: str) -> bool:
        try:
            settings_list = await self.client.list_agent_settings()
        except Exception:
            return True

        aliases = self.AGENT_SETTING_ALIASES.get(agent_type, {agent_type})
        for item in settings_list:
            if str(item.get("agent_type") or "") in aliases:
                return bool(item.get("enabled", True))
        return True
