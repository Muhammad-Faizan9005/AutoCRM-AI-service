from __future__ import annotations

import asyncio
from uuid import uuid4

from app.schemas.events import AgentEventIn
from app.services import planner_service as planner_module
from app.services.planner_service import PlannerService


def test_planner_fallback_for_deal_risk() -> None:
    planner = PlannerService()
    payload = AgentEventIn(
        event_type="deal_risk",
        entity_id=uuid4(),
        entity_type="deal",
        actor_id=str(uuid4()),
        metadata={"event_id": "e1"},
    )

    plan = asyncio.run(planner.plan_action(payload, {"score": 80}))

    assert plan.action_type == "create_alert"
    assert plan.recipient_id == payload.actor_id
    assert plan.requires_approval is False


def test_planner_uses_llm_json(monkeypatch) -> None:
    async def fake_generate(self, **kwargs):
        return '{"action_type":"create_task","reason":"Planned","title":"Call lead"}'

    monkeypatch.setattr(planner_module.LLMService, "generate", fake_generate)

    planner = PlannerService()
    payload = AgentEventIn(
        event_type="stale_lead",
        entity_id=uuid4(),
        entity_type="lead",
        actor_id=str(uuid4()),
        metadata={"event_id": "e2"},
    )

    plan = asyncio.run(planner.plan_action(payload, {"activity": "none"}))

    assert plan.action_type == "create_task"
    assert plan.reason == "Planned"
    assert plan.title == "Call lead"
