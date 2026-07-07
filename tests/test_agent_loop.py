from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.events import AgentEventIn
from app.schemas.planner import PlannedAction
from app.services import agent_loop as loop_module
from app.services.agent_loop import AgentLoop


def test_agent_loop_records_full_trace_and_creates_task(monkeypatch, sample_run_context) -> None:
    traces = []
    created = {}

    async def fake_context(self, entity_id, entity_type, **kwargs):
        return {"entity_snapshot": {"id": str(entity_id)}, "entity_memory": [], "rag_docs": []}

    async def fake_plan(self, payload, context):
        return PlannedAction(
            event_meaning="Lead needs follow-up.",
            selected_tool="create_task",
            action_type="create_task",
            reason="No recent activity",
            title="Call lead",
            description="Ask about next steps.",
        )

    async def fake_generate(self, **kwargs):
        return "Generated follow-up detail."

    async def fake_record(self, run_id, step, *, status="completed", payload=None):
        traces.append({"step": step, "status": status, "payload": payload or {}})

    async def fake_create_action(self, run_id, action):
        created["action"] = action
        return uuid4()

    monkeypatch.setattr(loop_module.ContextService, "build_context", fake_context)
    monkeypatch.setattr(loop_module.PlannerService, "plan_action", fake_plan)
    monkeypatch.setattr(loop_module.LLMService, "generate", fake_generate)
    monkeypatch.setattr(loop_module.RunTraceService, "record", fake_record)
    monkeypatch.setattr(loop_module.ActionManager, "create_action", fake_create_action)

    payload = AgentEventIn(
        event_type="stale_lead",
        entity_id=uuid4(),
        entity_type="lead",
        actor_id=str(uuid4()),
        metadata={"event_id": "loop-1"},
    )

    asyncio.run(AgentLoop().run(payload, sample_run_context))

    assert [trace["step"] for trace in traces] == [
        "event_received",
        "tool_registry_loaded",
        "context_built",
        "plan_made",
        "tool_chosen",
        "action_executed",
    ]
    assert traces[3]["payload"]["plan"]["selected_tool"] == "create_task"
    assert created["action"].action_type == "create_task"
    assert created["action"].data["title"] == "Call lead"


def test_agent_loop_creates_deal_alert_without_approval(monkeypatch, sample_run_context) -> None:
    created = {}

    async def fake_context(self, entity_id, entity_type, **kwargs):
        return {"entity_snapshot": {"id": str(entity_id), "amount": 10000}}

    async def fake_plan(self, payload, context):
        return PlannedAction(
            event_meaning="Deal has elevated risk.",
            selected_tool="create_alert",
            action_type="create_alert",
            reason="Deal risk detected",
            title="Deal risk alert",
            message="Review stalled deal.",
            recipient_id=payload.actor_id,
            requires_approval=False,
        )

    async def fake_record(self, run_id, step, *, status="completed", payload=None):
        return None

    async def fake_create_action(self, run_id, action):
        created["action"] = action
        return uuid4()

    monkeypatch.setattr(loop_module.ContextService, "build_context", fake_context)
    monkeypatch.setattr(loop_module.PlannerService, "plan_action", fake_plan)
    monkeypatch.setattr(loop_module.RunTraceService, "record", fake_record)
    monkeypatch.setattr(loop_module.ActionManager, "create_action", fake_create_action)

    actor_id = str(uuid4())
    payload = AgentEventIn(
        event_type="deal_risk",
        entity_id=uuid4(),
        entity_type="deal",
        actor_id=actor_id,
        metadata={"event_id": "loop-2"},
    )

    asyncio.run(AgentLoop().run(payload, sample_run_context))

    assert created["action"].action_type == "create_alert"
    assert created["action"].requires_approval is False
    assert created["action"].data["recipient_id"] == actor_id


def test_agent_loop_rejects_unsupported_events() -> None:
    payload = AgentEventIn(
        event_type="meeting_complete",
        entity_id=uuid4(),
        entity_type="lead",
        actor_id=str(uuid4()),
    )

    assert AgentLoop().supports(payload) is False
