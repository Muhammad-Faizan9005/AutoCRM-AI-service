"""add ai meeting transcripts

Revision ID: 0007_add_ai_meeting_transcripts
Revises: 0006_harden_ai_rls
Create Date: 2026-07-16 00:00:00.000000

Ports the full ai_meeting_transcripts DDL from
transcription_service.py:_ensure_schema() into a proper Alembic migration
so that non-dev environments no longer execute runtime DDL.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0007_add_ai_meeting_transcripts"
down_revision: Union[str, None] = "0006_harden_ai_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_meeting_transcripts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recording_id UUID NOT NULL UNIQUE,
            meeting_id UUID,
            entity_id UUID,
            entity_type VARCHAR(50) NOT NULL DEFAULT 'meeting',
            source_type VARCHAR(30) NOT NULL DEFAULT 'local_path',
            recording_path TEXT,
            recording_url TEXT,
            assemblyai_transcript_id TEXT,
            transcript_text TEXT,
            meeting_summary TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            error TEXT,
            last_attempted_at TIMESTAMPTZ,
            next_retry_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ai_meeting_transcripts_status
                CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            CONSTRAINT ck_ai_meeting_transcripts_source_type
                CHECK (source_type IN ('local_path', 'url'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_status "
        "ON ai_meeting_transcripts(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_meeting_id "
        "ON ai_meeting_transcripts(meeting_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_meeting_transcripts_last_attempted_at "
        "ON ai_meeting_transcripts(last_attempted_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ai_meeting_transcripts_last_attempted_at")
    op.execute("DROP INDEX IF EXISTS idx_ai_meeting_transcripts_meeting_id")
    op.execute("DROP INDEX IF EXISTS idx_ai_meeting_transcripts_status")
    op.execute("DROP TABLE IF EXISTS ai_meeting_transcripts")
