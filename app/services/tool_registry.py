from __future__ import annotations

from uuid import UUID

from app.schemas.actions import AgentAction
from app.services.autocrm_client import AutoCRMClient


class ToolRegistry:
    def __init__(self) -> None:
        self.client = AutoCRMClient()

    async def fetch_entity_snapshot(self, entity_id: UUID, entity_type: str) -> dict[str, object]:
        return await self.client.get_entity_snapshot(entity_type.strip().lower(), entity_id)

    def list_tools(self) -> list[dict[str, object]]:
        return [
            {"name": "fetch_lead", "kind": "read", "entity_type": "lead"},
            {"name": "fetch_deal", "kind": "read", "entity_type": "deal"},
            {"name": "fetch_user", "kind": "read", "entity_type": "user"},
            {"name": "create_task", "kind": "write", "requires_approval": False},
            {"name": "create_note", "kind": "write", "requires_approval": False},
            {"name": "create_alert", "kind": "write", "requires_approval": True},
        ]

    async def execute_read_tool(self, tool_name: str, entity_id: UUID) -> dict[str, object]:
        tool_to_entity = {
            "fetch_lead": "lead",
            "fetch_deal": "deal",
            "fetch_user": "user",
        }
        entity_type = tool_to_entity.get(tool_name)
        if entity_type is None:
            raise ValueError(f"Unsupported read tool: {tool_name}")
        return await self.fetch_entity_snapshot(entity_id, entity_type)

    def validate_action_tool(self, action: AgentAction) -> None:
        allowed = {"create_task", "create_note", "create_alert"}
        if action.action_type not in allowed:
            raise ValueError(f"Unsupported action tool: {action.action_type}")
        if action.action_type == "create_task" and not action.data.get("title"):
            raise ValueError("create_task requires a title")
        if action.action_type == "create_note" and not (action.data.get("title") or action.data.get("content")):
            raise ValueError("create_note requires a title or content")
        if action.action_type == "create_alert" and not action.data.get("recipient_id"):
            raise ValueError("create_alert requires a recipient_id")
