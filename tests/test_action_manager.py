from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.schemas.actions import AgentAction
from app.services import action_manager as action_module
from app.services.action_manager import ActionManager


def test_action_manager_auto_approves_alert(monkeypatch) -> None:
    calls = {}

    async def fake_backend_create_action(self, action):
        calls["action"] = action
        return {"action_id": str(uuid4())}

    monkeypatch.setattr(action_module.AutoCRMClient, "create_action", fake_backend_create_action)

    action = AgentAction(
        action_type="create_alert",
        entity_type="deal",
        entity_id=uuid4(),
        reason="Risk",
        data={"title": "Risk", "message": "Review", "recipient_id": str(uuid4())},
    )

    asyncio.run(ActionManager().create_action(uuid4(), action))

    assert calls["action"].approval_status == "auto_approved"
    assert calls["action"].action_type == "create_alert"
    assert calls["action"].run_id is not None


def test_action_manager_stores_pending_approval_for_task(monkeypatch) -> None:
    calls = {}

    async def fake_backend_create_action(self, action):
        calls["action"] = action
        return {"action_id": str(uuid4())}

    monkeypatch.setattr(action_module.AutoCRMClient, "create_action", fake_backend_create_action)

    action = AgentAction(
        action_type="create_task",
        entity_type="lead",
        entity_id=uuid4(),
        reason="Follow up",
        data={"title": "Call lead", "description": "Ask for next step"},
    )

    asyncio.run(ActionManager().create_action(uuid4(), action))

    assert calls["action"].approval_status == "pending"
    assert calls["action"].action_type == "create_task"


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
