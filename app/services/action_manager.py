from __future__ import annotations

from uuid import UUID, uuid4

from app.schemas.actions import AgentAction
from app.services.autocrm_client import AutoCRMClient
from app.services.tool_registry import ToolRegistry


class ActionManager:
    def __init__(self) -> None:
        self.client = AutoCRMClient()
        self.tools = ToolRegistry()

    async def create_action(self, run_id: UUID, action: AgentAction) -> UUID:
        self.tools.validate_action_tool(action)
        approval_status = "pending" if self._requires_approval(action) else "auto_approved"
        action.approval_status = approval_status
        action.run_id = str(run_id)
        if not action.idempotency_key:
            action.idempotency_key = f"{run_id}:{action.action_type}:{action.entity_type}:{action.entity_id}"
        result = await self.client.create_action(action)
        raw_action_id = result.get("action_id") or result.get("id")
        try:
            return UUID(str(raw_action_id))
        except (TypeError, ValueError):
            return uuid4()

    def _requires_approval(self, action: AgentAction) -> bool:
        if action.requires_approval is True:
            return True
        high_risk = {"send_email", "update_deal_stage", "update_lead_status"}
        return action.action_type in high_risk
