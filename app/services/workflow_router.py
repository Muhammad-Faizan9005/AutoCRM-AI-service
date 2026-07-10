from __future__ import annotations

from app.schemas.events import AgentEventIn
from app.workflows.deal_risk import DealRiskWorkflow
from app.workflows.daily_summary import DailySummaryWorkflow
from app.workflows.lead_nudge import LeadNudgeWorkflow
from app.workflows.meeting_intel import MeetingIntelWorkflow
from app.workflows.task_auto import TaskAutoWorkflow
from app.workflows.task_deadline_watch import TaskDeadlineWatchWorkflow


class WorkflowRouter:
    def resolve(self, payload: AgentEventIn):
        if payload.event_type == "stale_lead":
            return LeadNudgeWorkflow()
        if payload.event_type == "deal_risk":
            return DealRiskWorkflow()
        if payload.event_type == "daily_summary":
            return DailySummaryWorkflow()
        if payload.event_type == "task_auto":
            return TaskAutoWorkflow()
        if payload.event_type == "task_deadline_watch":
            return TaskDeadlineWatchWorkflow()
        if payload.event_type == "meeting_complete":
            return MeetingIntelWorkflow()
        return None
