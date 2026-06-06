"""add ai context chunks

Revision ID: 0005_add_ai_context_chunks
Revises: 0004_add_ai_run_traces
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_add_ai_context_chunks"
down_revision: Union[str, None] = "0004_add_ai_run_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ai_context_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE ai_context_chunks ALTER COLUMN embedding TYPE vector(384) USING embedding::vector")
    op.create_index("idx_ai_context_chunks_entity", "ai_context_chunks", ["entity_id", "entity_type"])
    op.execute(
        "CREATE INDEX idx_ai_context_chunks_embedding "
        "ON ai_context_chunks USING ivfflat (embedding vector_cosine_ops)"
    )
    op.execute("ALTER TABLE ai_context_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_context_chunks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_context_chunks_service_role_all ON ai_context_chunks "
        "FOR ALL TO service_role USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_context_chunks_service_role_all ON ai_context_chunks")
    op.execute("ALTER TABLE ai_context_chunks DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS idx_ai_context_chunks_embedding")
    op.drop_index("idx_ai_context_chunks_entity", table_name="ai_context_chunks")
    op.drop_table("ai_context_chunks")
