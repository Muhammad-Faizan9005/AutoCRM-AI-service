from __future__ import annotations

from alembic import op


revision = "0003_rename_agent_tables_to_ai"
down_revision = "0002_enable_rls_ai_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("agent_runs", "ai_runs")
    op.rename_table("agent_actions", "ai_actions")
    op.rename_table("approval_requests", "ai_approval_requests")
    op.execute("ALTER INDEX IF EXISTS uq_agent_action_dedup RENAME TO uq_ai_action_dedup")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS uq_ai_action_dedup RENAME TO uq_agent_action_dedup")
    op.rename_table("ai_approval_requests", "approval_requests")
    op.rename_table("ai_actions", "agent_actions")
    op.rename_table("ai_runs", "agent_runs")
