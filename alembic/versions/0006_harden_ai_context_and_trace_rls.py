"""harden ai context and trace rls

Revision ID: 0006_harden_ai_rls
Revises: 0005_add_ai_context_chunks
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0006_harden_ai_rls"
down_revision: Union[str, None] = "0005_add_ai_context_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_run_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_run_traces FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS ai_run_traces_service_role_all ON ai_run_traces")
    op.execute(
        "CREATE POLICY ai_run_traces_service_role_all ON ai_run_traces "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )

    op.execute("ALTER TABLE ai_context_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_context_chunks FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS ai_context_chunks_service_role_all ON ai_context_chunks")
    op.execute(
        "CREATE POLICY ai_context_chunks_service_role_all ON ai_context_chunks "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_context_chunks_service_role_all ON ai_context_chunks")
    op.execute("ALTER TABLE ai_context_chunks NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_context_chunks DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS ai_run_traces_service_role_all ON ai_run_traces")
    op.execute("ALTER TABLE ai_run_traces NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_run_traces DISABLE ROW LEVEL SECURITY")
