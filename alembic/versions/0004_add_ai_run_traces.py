"""add ai run traces

Revision ID: 0004_add_ai_run_traces
Revises: 0003_rename_agent_tables_to_ai
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_add_ai_run_traces"
down_revision: Union[str, None] = "0003_rename_agent_tables_to_ai"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_run_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_ai_run_traces_run_created", "ai_run_traces", ["run_id", "created_at"])
    op.execute("ALTER TABLE ai_run_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_run_traces FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_run_traces_service_role_all ON ai_run_traces "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_run_traces_service_role_all ON ai_run_traces")
    op.execute("ALTER TABLE ai_run_traces DISABLE ROW LEVEL SECURITY")
    op.drop_index("idx_ai_run_traces_run_created", table_name="ai_run_traces")
    op.drop_table("ai_run_traces")
