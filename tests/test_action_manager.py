from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.schemas.actions import AgentAction
from app.services import action_manager as action_module
from app.services.action_manager import ActionManager


def test_action_manager_stores_pending_approval_for_alert(monkeypatch) -> None:
    calls = {}

    async def fake_create_action(self, **kwargs):
        calls["action"] = kwargs

    async def fake_create_approval(self, **kwargs):
        calls["approval"] = kwargs

    async def fake_dispatch(self, action):
        calls["dispatch"] = action

    monkeypatch.setattr(action_module.AgentStore, "create_action", fake_create_action)
    monkeypatch.setattr(action_module.AgentStore, "create_approval_request", fake_create_approval)
    monkeypatch.setattr(action_module.AutoCRMClient, "dispatch_action", fake_dispatch)

    action = AgentAction(
        action_type="create_alert",
        entity_type="deal",
        entity_id=uuid4(),
        reason="Risk",
        data={"title": "Risk", "message": "Review", "recipient_id": str(uuid4())},
        requires_approval=True,
    )

    asyncio.run(ActionManager().create_action(uuid4(), action))

    assert calls["action"]["approval_status"] == "pending"
    assert calls["approval"]["fallback_policy"] == "skip"
    assert calls["dispatch"].action_type == "create_alert"


def test_action_manager_dispatches_auto_approved_task(monkeypatch) -> None:
    calls = {}

    async def fake_create_action(self, **kwargs):
        calls["action"] = kwargs

    async def fake_create_approval(self, **kwargs):
        calls["approval"] = kwargs

    async def fake_dispatch(self, action):
        calls["dispatch"] = action

    monkeypatch.setattr(action_module.AgentStore, "create_action", fake_create_action)
    monkeypatch.setattr(action_module.AgentStore, "create_approval_request", fake_create_approval)
    monkeypatch.setattr(action_module.AutoCRMClient, "dispatch_action", fake_dispatch)

    action = AgentAction(
        action_type="create_task",
        entity_type="lead",
        entity_id=uuid4(),
        reason="Follow up",
        data={"title": "Call lead", "description": "Ask for next step"},
    )

    asyncio.run(ActionManager().create_action(uuid4(), action))

    assert calls["action"]["approval_status"] == "auto_approved"
    assert calls["dispatch"].action_type == "create_task"
    assert "approval" not in calls


def test_action_manager_validates_required_payload() -> None:
    action = AgentAction(
        action_type="create_alert",
        entity_type="deal",
        entity_id=uuid4(),
        reason="Risk",
        data={"title": "Risk"},
    )

    with pytest.raises(ValueError, match="recipient_id"):
        asyncio.run(ActionManager().create_action(uuid4(), action))
