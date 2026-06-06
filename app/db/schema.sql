CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ai_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    entity_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(64) UNIQUE,
    summary TEXT,
    failure_cause VARCHAR,
    failure_detail TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ai_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES ai_runs(id) ON DELETE CASCADE,
    action_type VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    reason TEXT NOT NULL,
    payload JSONB NOT NULL,
    idempotency_key VARCHAR(64),
    approval_status VARCHAR NOT NULL DEFAULT 'auto_approved',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_action_dedup
    ON ai_actions (run_id, action_type, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS ai_run_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES ai_runs(id) ON DELETE CASCADE,
    step VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_run_traces_run_created
    ON ai_run_traces (run_id, created_at);

ALTER TABLE ai_run_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_run_traces FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_run_traces_service_role_all ON ai_run_traces;
CREATE POLICY ai_run_traces_service_role_all
    ON ai_run_traces FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

CREATE TABLE IF NOT EXISTS ai_context_chunks (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    entity_id UUID NOT NULL,
    entity_type VARCHAR NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR NOT NULL,
    source_id VARCHAR,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_context_chunks_entity
    ON ai_context_chunks (entity_id, entity_type);

CREATE INDEX IF NOT EXISTS idx_ai_context_chunks_embedding
    ON ai_context_chunks USING ivfflat (embedding vector_cosine_ops);

ALTER TABLE ai_context_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_context_chunks FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_context_chunks_service_role_all ON ai_context_chunks;
CREATE POLICY ai_context_chunks_service_role_all
    ON ai_context_chunks FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

CREATE TABLE IF NOT EXISTS ai_approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_action_id UUID REFERENCES ai_actions(id) ON DELETE CASCADE,
    requested_by VARCHAR NOT NULL,
    approver_id UUID,
    state VARCHAR NOT NULL DEFAULT 'pending',
    reason TEXT,
    approver_note TEXT,
    expires_at TIMESTAMPTZ,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    fallback_policy VARCHAR DEFAULT 'skip'
);
