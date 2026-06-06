from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PlannedAction(BaseModel):
    event_meaning: str = ""
    needs_more_context: bool = False
    selected_tool: Literal["create_task", "create_note", "create_alert"] | None = None
    action_type: Literal["create_task", "create_note", "create_alert"]
    reason: str
    title: str | None = None
    description: str | None = None
    message: str | None = None
    recipient_id: str | None = None
    requires_approval: bool | None = None
