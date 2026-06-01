from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.db.agent_store import AgentStore
from app.schemas.actions import AgentAction
from app.services.autocrm_client import AutoCRMClient


class ActionManager:
    def __init__(self) -> None:
        self.store = AgentStore()
        self.client = AutoCRMClient()

    async def create_action(self, run_id: UUID, action: AgentAction) -> UUID:
        action_id = uuid4()
        approval_status = "pending" if self._requires_approval(action) else "auto_approved"
        await self.store.create_action(
            action_id=action_id,
            run_id=run_id,
            action_type=action.action_type,
            entity_type=action.entity_type,
            entity_id=action.entity_id,
            reason=action.reason,
            payload=action.data,
            idempotency_key=action.idempotency_key,
            approval_status=approval_status,
        )

        if approval_status == "pending":
            await self.store.create_approval_request(
                request_id=uuid4(),
                agent_action_id=action_id,
                requested_by="agent.action@autocrm.internal",
                approver_id=None,
                reason=action.reason,
                expires_at=datetime.utcnow() + timedelta(hours=24),
                fallback_policy="skip",
            )
            return action_id

        await self.client.dispatch_action(action)
        return action_id

    def _requires_approval(self, action: AgentAction) -> bool:
        if action.requires_approval is True:
            return True
        high_risk = {"send_email", "update_deal_stage", "update_lead_status"}
        return action.action_type in high_risk
