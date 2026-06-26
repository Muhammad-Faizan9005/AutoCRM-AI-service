from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.events import AgentEventIn
from app.workflows.deal_risk import DealRiskWorkflow
from app.workflows.daily_summary import DailySummaryWorkflow
from app.workflows.lead_nudge import LeadNudgeWorkflow


def test_daily_summary_workflow_emits_note(monkeypatch, sample_run_context) -> None:
    captured = {}

    async def fake_build_context(self, entity_id, entity_type, **kwargs):
        return {"entity_id": entity_id, "entity_type": entity_type}

    async def fake_create_action(self, run_id, action):
        captured["action"] = action
        return uuid4()

    async def fake_llm(self, **kwargs):
        return "Summary content"

    async def fake_trace(self, run_id, *, step, status, payload):
        return {}

    monkeypatch.setattr("app.workflows.graph_runner.ContextService.build_context", fake_build_context)
    monkeypatch.setattr("app.workflows.graph_runner.ActionManager.create_action", fake_create_action)
    monkeypatch.setattr("app.workflows.graph_runner.AutoCRMClient.create_run_trace", fake_trace)
    monkeypatch.setattr("app.workflows.daily_summary.LLMService.generate", fake_llm)

    payload = AgentEventIn(event_type="daily_summary", entity_id=uuid4(), entity_type="user", actor_id=str(uuid4()))

    asyncio.run(DailySummaryWorkflow().run(payload, sample_run_context))

    assert captured["action"].action_type == "create_note"


def test_lead_nudge_workflow_emits_task(monkeypatch, sample_run_context) -> None:
    captured = {}

    async def fake_build_context(self, entity_id, entity_type, **kwargs):
        return {"entity_id": entity_id, "entity_type": entity_type}

    async def fake_create_action(self, run_id, action):
        captured["action"] = action
        return uuid4()

    async def fake_llm(self, **kwargs):
        return "Follow-up tomorrow"

    async def fake_trace(self, run_id, *, step, status, payload):
        return {}

    monkeypatch.setattr("app.workflows.graph_runner.ContextService.build_context", fake_build_context)
    monkeypatch.setattr("app.workflows.graph_runner.ActionManager.create_action", fake_create_action)
    monkeypatch.setattr("app.workflows.graph_runner.AutoCRMClient.create_run_trace", fake_trace)
    monkeypatch.setattr("app.workflows.lead_nudge.LLMService.generate", fake_llm)

    payload = AgentEventIn(event_type="stale_lead", entity_id=uuid4(), entity_type="lead", actor_id=str(uuid4()))

    asyncio.run(LeadNudgeWorkflow().run(payload, sample_run_context))

    assert captured["action"].action_type == "create_task"


def test_deal_risk_workflow_sets_alert_recipient(monkeypatch, sample_run_context) -> None:
    captured = {}
    actor_id = str(uuid4())

    async def fake_build_context(self, entity_id, entity_type, **kwargs):
        return {"entity_id": entity_id, "entity_type": entity_type}

    async def fake_create_action(self, run_id, action):
        captured["action"] = action
        return uuid4()

    async def fake_llm(self, **kwargs):
        return "High churn risk"

    async def fake_trace(self, run_id, *, step, status, payload):
        return {}

    monkeypatch.setattr("app.workflows.graph_runner.ContextService.build_context", fake_build_context)
    monkeypatch.setattr("app.workflows.graph_runner.ActionManager.create_action", fake_create_action)
    monkeypatch.setattr("app.workflows.graph_runner.AutoCRMClient.create_run_trace", fake_trace)
    monkeypatch.setattr("app.workflows.deal_risk.LLMService.generate", fake_llm)

    payload = AgentEventIn(event_type="deal_risk", entity_id=uuid4(), entity_type="deal", actor_id=actor_id)

    asyncio.run(DealRiskWorkflow().run(payload, sample_run_context))

    assert captured["action"].action_type == "create_alert"
    assert captured["action"].data["recipient_id"] == actor_id
