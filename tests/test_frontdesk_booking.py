"""Front desk booking safety: a refused calendar is never reported as booked."""
import asyncio
from datetime import datetime, timezone

from app.schemas.frontdesk import BookMeetingArgs, ListSlotsArgs
from app.workflows import frontdesk as fd

def test_book_meeting_requires_time_zone():
    """An unstated zone is what silently booked the wrong hour, so reject it."""
    base = {"starts_at": "2026-09-01T10:00:00+05:00", "ends_at": "2026-09-01T10:30:00+05:00"}
    try:
        BookMeetingArgs(**base)
        raise AssertionError("time_zone must be required")
    except Exception as exc:
        assert "time_zone" in str(exc)
    assert BookMeetingArgs(**base, time_zone="Asia/Karachi").time_zone == "Asia/Karachi"

def test_list_slots_is_a_registered_tool():
    assert "list_slots" in fd.ALLOWED_TOOLS
    assert ListSlotsArgs(day="2026-09-01T00:00:00+05:00").day.year == 2026

def test_unsynced_calendar_is_not_ok(monkeypatch):
    """A 200 with calendar_synced=false must surface as a failed booking."""
    slots = ["2026-09-01T09:00:00+05:00", "2026-09-01T09:30:00+05:00"]

    async def fake_appointment(payload):
        return {"appointment": {"starts_at": "2026-09-01T20:00:00+05:00"}, "calendar_synced": False,
                "calendar_error": "Cal.com rejected the booking (409): not available",
                "alternative_slots": slots}

    monkeypatch.setattr(fd._BACKEND, "create_appointment", fake_appointment)
    state = fd.FrontDeskState(session_id="s1")
    state.identity = fd.IdentityState(status="matched", lead_id="lead-1")
    decision = fd.FrontDeskDecision(tool="book_meeting", arguments={
        "starts_at": "2026-09-01T20:00:00+05:00", "ends_at": "2026-09-01T20:30:00+05:00",
        "time_zone": "Asia/Karachi"})
    result = asyncio.run(fd.FrontDeskWorkflow()._execute_tool("s1", state, decision))

    assert result["ok"] is False
    assert result["error"] == "calendar_rejected"
    assert state.stage != "completed"  # a refused slot does not close the conversation
    assert state.known_facts["offered_slots"] == slots

    reply = fd.FrontDeskWorkflow._template_reply("book_meeting", result)
    assert "booked" not in reply.lower()
    assert "9:00 AM" in reply  # the real openings, in business-local wording

def test_synced_calendar_confirms(monkeypatch):
    async def fake_appointment(payload):
        return {"appointment": {"starts_at": "2026-09-01T05:00:00+00:00"}, "calendar_synced": True,
                "provider": "cal.com"}

    monkeypatch.setattr(fd._BACKEND, "create_appointment", fake_appointment)
    state = fd.FrontDeskState(session_id="s2")
    state.identity = fd.IdentityState(status="matched", lead_id="lead-1")
    decision = fd.FrontDeskDecision(tool="book_meeting", arguments={
        "starts_at": "2026-09-01T10:00:00+05:00", "ends_at": "2026-09-01T10:30:00+05:00",
        "time_zone": "Asia/Karachi"})
    result = asyncio.run(fd.FrontDeskWorkflow()._execute_tool("s2", state, decision))

    assert result["ok"] is True
    assert state.stage == "completed"
    assert "booked" in fd.FrontDeskWorkflow._template_reply("book_meeting", result).lower()

def test_human_slots_render_in_business_time():
    # 05:00Z is 10:00 in Asia/Karachi: the visitor must never see the UTC hour.
    rendered = fd._human_slots(["2026-09-01T05:00:00Z"])
    assert "10:00 AM" in rendered

def test_now_line_carries_both_clocks():
    line = fd._now_line()
    assert "business time" in line and "UTC" in line
