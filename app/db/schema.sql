CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
