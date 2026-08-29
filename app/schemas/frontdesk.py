"""Front desk runtime state and tool contracts.

The Pydantic models in this module mirror the backend's internal contracts
(/api/internal/frontdesk/*). Their JSON schemas are injected into the prompt so
the model generates schema-compliant arguments, and the same models validate
the generated objects before the AI service calls the backend.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Runtime state (persisted on the backend session row via PUT .../state)
# ---------------------------------------------------------------------------

class IdentityState(BaseModel):
    status: Literal["unknown", "matched", "created", "unmatched", "ambiguous"] = "unknown"
    lead_id: str | None = None
    owner_id: str | None = None
    matched_by: str | None = None

class FrontDeskState(BaseModel):
    session_id: str
    channel: str = "web_chat"
    persona: str = "frontdesk_discovery"
    stage: Literal[
        "greeting", "identity", "business_context", "problem",
        "qualification", "meeting_offer", "handoff", "completed",
    ] = "greeting"
    known_facts: dict[str, Any] = Field(default_factory=dict)
    missing_facts: list[str] = Field(default_factory=list)
    identity: IdentityState = Field(default_factory=IdentityState)
    last_questions: list[str] = Field(default_factory=list, max_length=5)
    last_action: dict[str, Any] | None = None
    completed_stages: list[str] = Field(default_factory=list)
    conversation_summary: str = ""

# ---------------------------------------------------------------------------
# Tool arguments (must validate against backend internal contracts)
# ---------------------------------------------------------------------------

class UpsertLeadArgs(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)

class SaveNoteArgs(BaseModel):
    content: str = Field(..., min_length=3, max_length=5000)

class CreateTaskArgs(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_at: datetime | None = None
    suggested_assignee_id: UUID | None = None

class RequestHandoffArgs(BaseModel):
    reason: str = Field(..., min_length=2, max_length=1000)
    summary: str | None = Field(default=None, max_length=5000)
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    suggested_assignee_id: UUID | None = None

class ListSlotsArgs(BaseModel):
    """Ask the calendar what is actually open on a day."""
    day: datetime
    time_zone: str | None = Field(default=None, max_length=64)

class BookMeetingArgs(BaseModel):
    provider: str = Field(default="internal", max_length=30)
    uid: str | None = Field(default=None, max_length=255)
    starts_at: datetime
    ends_at: datetime
    meeting_url: str | None = Field(default=None, max_length=2000)
    title: str = Field(default="Discovery meeting", max_length=255)
    # Required: a bare clock time with no zone is what silently books the wrong
    # hour. Copy the offset from the slot the visitor picked.
    time_zone: str = Field(..., max_length=64)
    summary: str | None = Field(default=None, max_length=5000)
    requested_task: dict[str, Any] | None = None

TOOL_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "upsert_lead": UpsertLeadArgs,
    "save_note": SaveNoteArgs,
    "create_task": CreateTaskArgs,
    "request_handoff": RequestHandoffArgs,
    "list_slots": ListSlotsArgs,
    "book_meeting": BookMeetingArgs,
}

ALLOWED_TOOLS = {"answer", *TOOL_ARGUMENT_MODELS.keys()}

def tool_contracts() -> dict[str, Any]:
    """JSON schemas for every tool, injected into the prompt."""
    schemas: dict[str, Any] = {"answer": {"type": "object", "properties": {}, "additionalProperties": False}}
    for name, model in TOOL_ARGUMENT_MODELS.items():
        schemas[name] = model.model_json_schema()
    return schemas

# ---------------------------------------------------------------------------
# Decision output (the model's JSON response)
# ---------------------------------------------------------------------------

class FrontDeskDecision(BaseModel):
    extracted_facts: dict[str, Any] = Field(default_factory=dict)
    stage: str = "greeting"
    tool: str = "answer"
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    reply: str = ""
