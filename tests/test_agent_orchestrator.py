from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.events import AgentEventIn
from app.services import agent_orchestrator as orchestrator_module
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.run_manager import RunContext


def test_orchestrator_runs_supported_event_to_completion(monkeypatch) -> None:
    calls = []
    run_context = RunContext(
        run_id=uuid4(),
        backend_run_id=uuid4(),
        trigger_type="stale_lead",
        entity_id=uuid4(),
        entity_type="lead",
        idempotency_key="event:orchestrator-1",
    )

    async def fake_start(self, payload):
        calls.append("start_run")
        return run_context

    async def fake_workflow_run(self, payload, context):
        calls.append("execute_agent_loop")

    async def fake_complete(self, run_id, status, summary=None, failure_cause=None, failure_detail=None):
        calls.append(("complete_run", status, summary))

    async def fake_trace(self, run_id, *, step, status, payload):
        return {}

    monkeypatch.setattr(orchestrator_module.RunManager, "start_run", fake_start)
    class FakeWorkflow:
        async def run(self, payload, context):
            await fake_workflow_run(self, payload, context)

    monkeypatch.setattr(orchestrator_module.WorkflowRouter, "resolve", lambda self, payload: FakeWorkflow())
    monkeypatch.setattr(orchestrator_module.RunManager, "complete_run", fake_complete)
    monkeypatch.setattr(orchestrator_module.AutoCRMClient, "create_run_trace", fake_trace)

    payload = AgentEventIn(
        event_type="stale_lead",
        entity_id=run_context.entity_id,
        entity_type="lead",
        actor_id=str(uuid4()),
    )

    asyncio.run(AgentOrchestrator().handle_event(payload))

    assert calls == [
        "start_run",
        "execute_agent_loop",
        ("complete_run", "completed", "lead_assistant completed"),
    ]


def test_orchestrator_skips_unsupported_event(monkeypatch) -> None:
    calls = []

    async def fake_start(self, payload):
        calls.append("start_run")

    monkeypatch.setattr(orchestrator_module.RunManager, "start_run", fake_start)

    payload = AgentEventIn(
        event_type="unknown_event",
        entity_id=uuid4(),
        entity_type="lead",
        actor_id=str(uuid4()),
    )

    asyncio.run(AgentOrchestrator().handle_event(payload))

    assert calls == []


def test_orchestrator_marks_run_failed_when_agent_loop_fails(monkeypatch) -> None:
    completions = []
    run_context = RunContext(
        run_id=uuid4(),
        backend_run_id=uuid4(),
        trigger_type="deal_risk",
        entity_id=uuid4(),
        entity_type="deal",
        idempotency_key="event:orchestrator-2",
    )

    async def fake_start(self, payload):
        return run_context

    async def fake_workflow_run(self, payload, context):
        raise RuntimeError("planner exploded")

    async def fake_complete(self, run_id, status, summary=None, failure_cause=None, failure_detail=None):
        completions.append(
            {
                "status": status,
                "summary": summary,
                "failure_cause": failure_cause,
                "failure_detail": failure_detail,
            }
        )

    async def fake_trace(self, run_id, *, step, status, payload):
        return {}

    monkeypatch.setattr(orchestrator_module.RunManager, "start_run", fake_start)
    class FakeWorkflow:
        async def run(self, payload, context):
            await fake_workflow_run(self, payload, context)

    monkeypatch.setattr(orchestrator_module.WorkflowRouter, "resolve", lambda self, payload: FakeWorkflow())
    monkeypatch.setattr(orchestrator_module.RunManager, "complete_run", fake_complete)
    monkeypatch.setattr(orchestrator_module.AutoCRMClient, "create_run_trace", fake_trace)

    payload = AgentEventIn(
        event_type="deal_risk",
        entity_id=run_context.entity_id,
        entity_type="deal",
        actor_id=str(uuid4()),
    )

    asyncio.run(AgentOrchestrator().handle_event(payload))

    assert completions == [
        {
            "status": "failed",
            "summary": None,
            "failure_cause": "AGENT_LOOP_ERROR",
            "failure_detail": "planner exploded",
        }
    ]


def test_orchestrator_skips_disabled_agent(monkeypatch) -> None:
    calls = []

    async def fake_settings(self):
        return [{"agent_type": "lead_assistant", "enabled": False}]

    async def fake_start(self, payload):
        calls.append("start_run")

    monkeypatch.setattr(orchestrator_module.AutoCRMClient, "list_agent_settings", fake_settings)
    monkeypatch.setattr(orchestrator_module.RunManager, "start_run", fake_start)

    payload = AgentEventIn(
        event_type="stale_lead",
        entity_id=uuid4(),
        entity_type="lead",
        actor_id=str(uuid4()),
    )

    asyncio.run(AgentOrchestrator().handle_event(payload))

    assert calls == []
