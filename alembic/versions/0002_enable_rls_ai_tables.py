from __future__ import annotations

from alembic import op


revision = "0002_enable_rls_ai_tables"
down_revision = "0001_create_agent_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_actions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY")

    op.execute(
        "CREATE POLICY agent_runs_service_role_all ON agent_runs "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY agent_actions_service_role_all ON agent_actions "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )
    op.execute(
        "CREATE POLICY approval_requests_service_role_all ON approval_requests "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS approval_requests_service_role_all ON approval_requests")
    op.execute("DROP POLICY IF EXISTS agent_actions_service_role_all ON agent_actions")
    op.execute("DROP POLICY IF EXISTS agent_runs_service_role_all ON agent_runs")

    op.execute("ALTER TABLE approval_requests DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_actions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_runs DISABLE ROW LEVEL SECURITY")
