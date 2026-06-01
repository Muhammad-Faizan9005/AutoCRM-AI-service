from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_create_agent_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=64), unique=True),
        sa.Column("summary", sa.Text()),
        sa.Column("failure_cause", sa.String()),
        sa.Column("failure_detail", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "agent_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64)),
        sa.Column("approval_status", sa.String(), nullable=False, server_default="auto_approved"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index(
        "uq_agent_action_dedup",
        "agent_actions",
        ["run_id", "action_type", "entity_type", "entity_id"],
        unique=True,
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_action_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_actions.id", ondelete="CASCADE")),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True)),
        sa.Column("state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text()),
        sa.Column("approver_note", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("fallback_policy", sa.String(), server_default="skip"),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_index("uq_agent_action_dedup", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_table("agent_runs")
