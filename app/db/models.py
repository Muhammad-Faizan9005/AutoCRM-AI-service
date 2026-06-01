from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AgentRun(Base):
    __tablename__ = "ai_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    trigger_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="pending")
    idempotency_key = Column(String(64), unique=True)
    summary = Column(Text)
    failure_cause = Column(String)
    failure_detail = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))


class AgentAction(Base):
    __tablename__ = "ai_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"))
    action_type = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    idempotency_key = Column(String(64))
    approval_status = Column(String, nullable=False, server_default="auto_approved")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    __tablename__ = "ai_approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    agent_action_id = Column(UUID(as_uuid=True), ForeignKey("agent_actions.id", ondelete="CASCADE"))
    requested_by = Column(String, nullable=False)
    approver_id = Column(UUID(as_uuid=True))
    state = Column(String, nullable=False, server_default="pending")
    reason = Column(Text)
    approver_note = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    decided_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    fallback_policy = Column(String, server_default="skip")
