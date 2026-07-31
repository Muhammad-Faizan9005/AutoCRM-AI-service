# AutoCRM AI Service Implementation (Detailed)

Last updated: 2026-07-29

This document describes the current AI service implementation. For each feature you will see:
- Why: the business or operational reason the capability exists.
- How: the runtime flow and important constraints.
- Where: the exact source files that implement the behavior.

Paths are relative to this file (`AI_service/Autocrm_AI_system/docs/`).

## 1) System overview

The AutoCRM AI service is a standalone FastAPI process that runs proactive CRM workflows. It reacts to inbound events and scheduled sweeps, gathers context from the backend and a RAG index, plans an action with an LLM, and dispatches that action back to the AutoCRM backend for approval and persistence. It never writes CRM rows itself.

Why
- Keep LLM inference, embeddings, vector search, and transcription out of the request path of the CRM API.
- Let the agent run on its own schedule (sweeps, cron jobs, transcription callbacks) without a user request driving it.
- Preserve a single authorization boundary: the backend owns runs, actions, approvals, and CRM writes.

How
- FastAPI app with a lifespan that initializes the DB pool, runs startup checks, then starts APScheduler.
- One inbound event is orchestrated by a LangGraph state machine that owns run lifecycle.
- Each workflow is a second, smaller LangGraph (build context -> build action -> dispatch) or a direct procedure.
- All backend communication goes through a single HTTP client using AI service credentials.

Where
- App setup and lifespan: [../app/main.py](../app/main.py)
- Route registration: [../app/api/router.py](../app/api/router.py)
- Settings: [../app/config.py](../app/config.py)
- Orchestrator: [../app/services/agent_orchestrator.py](../app/services/agent_orchestrator.py)
- Workflows: [../app/workflows](../app/workflows)
- Services: [../app/services](../app/services)
- Cross-cutting core: [../app/core](../app/core)

## 2) Startup sequence and fail-fast checks

Why
- A misconfigured provider used to surface hours later, mid-job, when a scheduled sweep happened to fire. Configuration problems should abort at boot instead.

How
- Lifespan order: configure logging -> init asyncpg pool -> `verify_security_config()` -> `verify_provider_config()` -> `verify_backend_connectivity()` -> register jobs and start scheduler.
- `verify_security_config()` raises if `AI_SERVICE_WEBHOOK_TOKEN` is unset outside development.
- `verify_provider_config()` validates only the credentials for providers that are actually enabled: `OPENAI_API_KEY` when `LLM_PROVIDER=openai`, `HUGGINGFACE_API_TOKEN` when `EMBEDDING_PROVIDER=huggingface`, and always the AssemblyAI key plus SDK importability. It warns in dev and raises in production.
- `verify_backend_connectivity()` requires `AUTOCRM_BASE_URL` and `AUTOCRM_AI_SERVICE_TOKEN`, then posts a heartbeat. Failure marks the service not-ready and aborts startup only when `AI_BACKEND_CONNECTIVITY_REQUIRED=true`.
- The scheduler starts only when `SCHEDULER_ENABLED=true` **and** the backend heartbeat succeeded, so a disconnected service does not fan out failing jobs.
- The lazy mid-request config guards that these checks replaced are kept commented in the services as reference, not deleted.

Where
- Lifespan: [../app/main.py](../app/main.py)
- Startup checks: [../app/core/startup_checks.py](../app/core/startup_checks.py)
- Readiness state: [../app/core/readiness.py](../app/core/readiness.py)
- Connection pool: [../app/db/pool.py](../app/db/pool.py)

## 3) API surface and authentication

Why
- The service exposes callbacks that trigger real CRM work, so everything except liveness must be authenticated, but liveness/readiness must stay cheap and public for orchestrators.

How
- `GET /health` and `GET /health/ready` are public. Readiness returns 503 with a state snapshot until the backend and database are both connected.
- Every other endpoint depends on `require_webhook_token`, which compares the `X-AutoCRM-AI-Webhook-Token` header against `AI_SERVICE_WEBHOOK_TOKEN`. The check is bypassed only when the token is unset **and** `APP_ENV` is `development`/`dev`/`test`.
- Protected endpoints: `POST /agent/events`, `GET /agent/runs/{run_id}`, `GET /agent/runs/{run_id}/trace`, the four `/transcriptions/*` routes, `GET /health/config`, and `GET /metrics`.
- Run reads are proxies: the service fetches run status and traces from the backend rather than its own tables.

Where
- Token dependency: [../app/api/dependencies.py](../app/api/dependencies.py)
- Event ingest: [../app/api/routes/events.py](../app/api/routes/events.py)
- Health and config: [../app/api/routes/health.py](../app/api/routes/health.py)
- Run reads: [../app/api/routes/runs.py](../app/api/routes/runs.py)
- Transcription callbacks: [../app/api/routes/transcriptions.py](../app/api/routes/transcriptions.py)
- Metrics: [../app/api/routes/metrics.py](../app/api/routes/metrics.py)

## 4) Backend authentication and the control-plane contract

Why
- The backend is the source of truth for runs, traces, actions, approvals, and CRM records. If the AI service wrote CRM rows directly it would bypass RBAC and leave no audit trail.

How
- Outbound calls send `X-AI-Service-Token` (the raw token issued from Profile Settings -> Developer Mode) and optionally `X-AI-Agent-Key` for runtime attribution. The agent key is not the token owner.
- `AutoCRMAuth` raises immediately if the service token is unset, so an unauthenticated call is never attempted.
- The client creates runs with a stable external run ID, appends trace steps, dispatches actions to `/api/agent/actions`, and reads workflow feeds. It never queries CRM tables.
- Backend feeds consumed: entity snapshots, entity memory, RAG document snapshots and reconciliation, stale-lead candidates, deal-risk candidates, summary candidates and per-user summary context, task deadline candidates/sweep/alerts, agent settings, the AI agent registry, lead score sweep, and the heartbeat.
- Every call uses `follow_redirects=True` with `AUTOCRM_AUTH_TIMEOUT`; batch operations (deadline sweep, lead score sweep) use the larger `AUTOCRM_BATCH_TIMEOUT`.

Where
- Auth headers: [../app/core/security.py](../app/core/security.py)
- HTTP client and all backend endpoints: [../app/services/autocrm_client.py](../app/services/autocrm_client.py)
- Action schema sent to the backend: [../app/schemas/actions.py](../app/schemas/actions.py)

## 5) Orchestration: the outer LangGraph

Why
- Lifecycle decisions (is this event supported, is the agent enabled, is this a duplicate, did the run succeed) must be deterministic and separate from the agent's reasoning, so a model failure can never leave a run in an ambiguous state.

How
- `AgentOrchestrator` compiles a LangGraph with nodes `interpret_event -> start_run -> execute_agent_loop -> complete_run | fail_run`.
- `interpret_event` maps `event_type` to an agent type via `AGENT_EVENT_MAP` and checks the backend's agent settings. Unknown or disabled agents end the graph without creating a run. If the settings fetch fails, the agent is treated as enabled rather than silently skipped.
- `AGENT_SETTING_ALIASES` lets one logical agent match several historical setting names (`lead_assistant` also matches `stale_lead`, `lead_nudge`).
- `start_run` delegates to `RunManager`; a run the backend reports as already completed/failed/cancelled ends the graph as a duplicate.
- `execute_agent_loop` prefers a specialized workflow from `WorkflowRouter` and falls back to the generic `AgentLoop`.
- Failures are classified into a structured `failure_cause`, recorded as a trace step, and the raw error message is included only when `is_dev`; production gets a generic message and the detail stays in the logs.
- A correlation ID is created at event ingress and the run ID is set once the run exists; both are injected into every log line.

Where
- Orchestrator graph: [../app/services/agent_orchestrator.py](../app/services/agent_orchestrator.py)
- Workflow routing: [../app/services/workflow_router.py](../app/services/workflow_router.py)
- Correlation context: [../app/core/correlation.py](../app/core/correlation.py)
- Logging filter: [../app/core/logging.py](../app/core/logging.py)
- Failure categories: [../app/core/failure.py](../app/core/failure.py)

## 6) Run lifecycle and idempotency

Why
- Sweeps re-scan the same candidates every few hours. Without a deterministic key, the same stale lead would produce a duplicate run and a duplicate task on every pass.

How
- `RunManager.start_run` builds an idempotency key from `event_type`, `entity_id`, and a window bucket, SHA-256 hashes it, then derives a deterministic run UUID with `uuid5`.
- Window bucket precedence: explicit `event_id` in metadata, then `recording_id`, then a daily bucket for `daily_summary`, otherwise an hourly bucket. So a lead can produce at most one run per hour and a user one summary run per day.
- The backend returns the canonical run; if its status is already terminal the orchestrator skips execution.
- `complete_run` writes status, summary, and on failure the structured cause and detail.

Where
- Run manager and window buckets: [../app/services/run_manager.py](../app/services/run_manager.py)
- Idempotency key: [../app/core/idempotency.py](../app/core/idempotency.py)

## 7) Context assembly (RAG + memory + snapshot)

Why
- The model needs grounded, entity-specific evidence, and it needs it inside a token budget. Unbounded context both costs money and degrades output quality.

How
- `ContextService.build_context` fetches three things: the backend entity snapshot, entity memory (previous AI actions and their approval outcomes), and RAG documents.
- A retrieval query is synthesized from event type, entity type, snapshot fields (name, title, status, stage, company, email), the three most recent memory entries, and string metadata values.
- Candidate entity IDs expand from the entity itself to its `organization_id`, `customer_id`, and `lead_id`; more than one candidate switches retrieval to a filtered global search.
- `daily_summary` for a user or agent takes a different path: it pulls `owned_leads`, `owned_deals`, and `tasks` from the backend summary-context endpoint, compacts each to a whitelist of fields, and runs an owner-scoped global retrieval with a larger `top_k`.
- Every path budgets the result: documents are capped at `rag_top_k` (10 for daily summary) and each document's content is truncated to 900 characters (700 for daily summary).
- Memory is capped at five entries per entity.

Where
- Context assembly: [../app/services/context_service.py](../app/services/context_service.py)
- Entity memory: [../app/services/memory_service.py](../app/services/memory_service.py)
- Entity snapshot tool: [../app/services/tool_registry.py](../app/services/tool_registry.py)

## 8) RAG: chunking, embeddings, and vector stores

Why
- Workflows need CRM history (notes, calls, prior deals) that is not in the entity row itself, retrievable without querying the backend's tables.

How
- `TextChunker` normalizes whitespace and splits into `RAG_CHUNK_SIZE` (900) character chunks with `RAG_CHUNK_OVERLAP` (120) overlap.
- Document IDs are stable: when a `source_id` exists the ID is a SHA-256 of `entity_type:entity_id:source:source_id`, so re-indexing the same backend row replaces its chunks instead of duplicating them. Without a `source_id` the ID includes a content hash plus a random suffix.
- `add_document` deletes the prior document by ID before upserting new chunks.
- Three vector store backends behind one interface, selected by `VECTOR_STORE`: `faiss` (persistent index on disk, guarded by an asyncio lock, rebuilt and pickled on every mutation), `pgvector`/`postgres` (the `ai_context_chunks` table with `<=>` cosine distance), and `memory` (the default; a process-local dict, for tests and local runs).
- Retrieval filters on source, owner, and candidate entity IDs. The in-memory store adds a +0.20 score boost for chunks belonging to the query's own entity so entity-specific context outranks generic matches.
- Two embedding providers: a deterministic local hashing embedder (no network, used for dev/tests) and a sentence-transformers model loaded through a process-wide cache so the model is loaded once per process, not per call. Both return L2-normalized vectors.

Where
- Chunking and document lifecycle: [../app/services/rag_service.py](../app/services/rag_service.py)
- Vector store implementations: [../app/services/vector_store.py](../app/services/vector_store.py)
- Embedding providers: [../app/services/embedding_service.py](../app/services/embedding_service.py)
- RAG schemas: [../app/schemas/rag.py](../app/schemas/rag.py)

## 9) RAG synchronization

Why
- The index must track the backend without re-reading the whole CRM on every pass, and it must forget records the backend deleted.

How
- `RagSyncService` walks eight sources — lead, deal, task, note, call, user, organization, customer — and requests each one's snapshot with a per-source `changed_since` cursor and `RAG_SYNC_BATCH_SIZE` limit.
- Cursors advance to the newest `updated_at` seen and persist to `RAG_SYNC_STATE_FILE` so a restart resumes rather than re-indexing.
- A `RAG_SYNC_MIN_DELAY_SECONDS` sleep between documents throttles embedding work so a large sync does not starve the event loop.
- A per-document failure is logged and skipped; it does not abort the batch.
- After indexing, `reconcile_deleted_sources` lists indexed `(source_table, source_id)` pairs, asks the backend which are missing, and deletes those chunks.

Where
- Sync service: [../app/services/rag_sync_service.py](../app/services/rag_sync_service.py)
- Backend snapshot and reconcile calls: [../app/services/autocrm_client.py](../app/services/autocrm_client.py)
- Persisted cursor: [../storage/rag_sync_state.json](../storage/rag_sync_state.json)

## 10) Prompt composition and injection defense

Why
- CRM data is user-supplied and reaches the model verbatim. A note or transcript containing "ignore your instructions" must be treated as data, never as instruction.

How
- `load_prompt` composes every prompt in a fixed order: `system.md`, `guardrails.md`, the per-workflow file, then the context wrapped in an explicit untrusted-data preamble and `<untrusted_context>` tags. A missing workflow file degrades to an empty section rather than an error.
- `system.md` defines the agent's role, names the context keys it can expect, sets conflict-resolution rules (backend snapshot beats RAG snippet; explicit customer statement beats generic summary), and forbids mentioning internal implementation details.
- `guardrails.md` covers evidence rules (no invented people, prices, dates, or commitments), action safety (which actions always require approval and which may auto-create), tone (plain text, no markdown or emoji, so output renders directly in CRM cards), data handling, and a per-workflow failure mode.
- Meeting transcripts are wrapped in their own `<untrusted_transcript>` block before summarization.
- Defense is layered: the prompt discourages bad output, and `action_policy` mechanically rejects it afterwards.

Where
- Prompt loader: [../app/prompts/loader.py](../app/prompts/loader.py)
- System prompt: [../app/prompts/system.md](../app/prompts/system.md)
- Guardrails: [../app/prompts/guardrails.md](../app/prompts/guardrails.md)
- Per-workflow prompts: [../app/prompts/workflows](../app/prompts/workflows)

## 11) LLM invocation, retry, and circuit breaking

Why
- Ollama and OpenAI fail independently of this service. A dead provider should fail fast rather than absorb retries from every concurrent workflow.

How
- `LLMService.generate` returns an empty string immediately when `LLM_ENABLED=false`, composes the prompt when a workflow is named, resolves the model from the tier (`small`/`large`), and dispatches to the Ollama or OpenAI transport. Any other provider raises.
- Each call passes through: circuit breaker check -> `retry_async` -> transport -> record success/failure -> observe latency in a `finally`, so latency is recorded even on failure.
- `retry_async` uses AWS full-jitter backoff: `delay = uniform(0, min(max_delay, base_delay * 2**(attempt-1)))`.
- `is_retryable` is the single source of truth: retry on timeouts, connect errors, and HTTP 429/500/502/503/504. Never retry 401/403 (auth), 400/404/422 (bad request or model), or our own `RuntimeError` configuration failures.
- The circuit breaker is a three-state machine (closed -> open -> half-open -> closed) per provider, guarded by an asyncio lock. After `failure_threshold` consecutive failures it rejects immediately with `CircuitOpenError` for `reset_timeout_seconds`, then allows one trial request.
- Retry policy and breaker config are resolved per provider from settings, with per-provider overrides falling back to defaults (`LLM_RETRY__OLLAMA__*`, `CIRCUIT_BREAKER__OPENAI__*`, etc.).
- Both transports send bounded generation (`temperature=0.2`, ~700 output tokens) and set native JSON mode when `json_mode=True`.

Where
- LLM service: [../app/services/llm_service.py](../app/services/llm_service.py)
- Retry and classification: [../app/core/retry.py](../app/core/retry.py)
- Circuit breaker: [../app/core/circuit_breaker.py](../app/core/circuit_breaker.py)
- Per-provider policy resolution: [../app/config.py](../app/config.py)

## 12) Planning and action policy

Why
- The planner is the point where model output becomes a proposed CRM write. Its output must be constrained mechanically, not just by prompt instruction.

How
- `PlannerService.plan_action` builds a fallback plan first, then asks the small model for JSON with a fixed key set and parses it into `PlannedAction`.
- Malformed JSON or validation failure logs a warning, increments `planner_failures_total`, and falls back to a hand-written plan per event type. Transport, circuit, and retry-exhausted errors are deliberately **not** caught here — they propagate so the orchestrator marks the run failed rather than silently shipping a fallback action.
- `_normalize_plan` fills the selected tool, recipient, reason, and event meaning, then runs `validate_planned_action`.
- `validate_planned_action` enforces three rules: `action_type`/`selected_tool` must be in `{create_task, create_note, create_alert}` (anything else is coerced to `create_task`), `create_task` always requires approval regardless of what the model returned, and `recipient_id` is restricted to the actor or empty so the model cannot target an arbitrary user.
- Notes and alerts default to not requiring approval when the model leaves it unset.

Where
- Planner: [../app/services/planner_service.py](../app/services/planner_service.py)
- Policy enforcement: [../app/services/action_policy.py](../app/services/action_policy.py)
- Plan schema: [../app/schemas/planner.py](../app/schemas/planner.py)
- Planner prompt: [../app/prompts/workflows/planner.md](../app/prompts/workflows/planner.md)

## 13) Tool registry and action dispatch

Why
- The agent must only reach for a known, validated set of capabilities, and every write must carry an idempotency key before it leaves the process.

How
- `ToolRegistry.list_tools` declares three read tools (`fetch_lead`, `fetch_deal`, `fetch_user`) and three write tools (`create_task`, `create_note`, `create_alert`) with their approval defaults. The list is recorded in the run trace so a reviewer can see what the agent could have done.
- `validate_action_tool` rejects unknown action types and enforces per-type required fields: a task needs a title, a note needs a title or content, an alert needs a recipient.
- `ActionManager.create_action` validates, resolves approval status, stamps `run_id`, and defaults the idempotency key to `{run_id}:{action_type}` when the workflow did not supply one.
- Approval is required when the action says so **or** when its type is in the high-risk set (`create_task`, `send_email`, `update_deal_stage`, `update_lead_status`); otherwise the status is `auto_approved`. The backend still makes the final call.
- The backend's returned action ID is parsed as a UUID, with a generated UUID as fallback so a malformed response cannot crash the run.

Where
- Tool registry: [../app/services/tool_registry.py](../app/services/tool_registry.py)
- Action manager: [../app/services/action_manager.py](../app/services/action_manager.py)

## 14) Run tracing and redaction

Why
- Traces are the audit record for autonomous behavior, and they are stored in a database that outlives the run. They must not become a PII archive.

How
- `RunTraceService.record` runs every payload through `_safe_trace_value` before sending it to the backend.
- Redaction is key-substring based: any key containing `authorization`, `password`, `token`, `api_key`, `secret`, `recording_path`, `transcript`, `transcript_text`, `email`, `phone`, `recording_url`, or `assemblyai_transcript_id` becomes `[redacted]`.
- Truncation bounds the rest: strings at 600 characters, lists at 5 items (with a "N more items" marker), dicts at 20 keys, and recursion at depth 4.
- The generic agent loop emits a fixed trace sequence: `event_received`, `tool_registry_loaded`, `context_built`, `plan_made`, `tool_chosen`, `action_executed`. Graph-based workflows emit `build_context`, `build_action`, and `dispatch_action`, each with started/completed/failed status.
- A nightly job deletes `ai_run_traces` rows older than `AI_TRACE_RETENTION_DAYS` (default 30).

Where
- Redaction and trace recording: [../app/services/run_trace_service.py](../app/services/run_trace_service.py)
- Trace steps in the generic loop: [../app/services/agent_loop.py](../app/services/agent_loop.py)
- Trace steps in graph workflows: [../app/workflows/graph_runner.py](../app/workflows/graph_runner.py)
- Retention sweep: [../app/core/jobs.py](../app/core/jobs.py)

## 15) Workflows

All graph-based workflows share `GraphRunner`, which compiles a two-node LangGraph (`build_context -> build_action`) and handles tracing and dispatch. An action factory returning `None` records a `no_action` decision and dispatches nothing.

Where (shared)
- Graph runner: [../app/workflows/graph_runner.py](../app/workflows/graph_runner.py)
- Base class: [../app/workflows/base.py](../app/workflows/base.py)
- Generic fallback loop: [../app/services/agent_loop.py](../app/services/agent_loop.py)

### 15.1 Lead nudge (`stale_lead`)

Why
- Leads with no recent activity go cold; a rep needs a specific, grounded reason to re-engage rather than a generic reminder.

How
- Before anything else it checks entity memory for a non-rejected `create_task` inside `LEAD_NUDGE_TASK_COOLDOWN_HOURS` (default 72) and returns no action if one exists. A memory entry with an unparseable timestamp is treated as recent — it suppresses rather than duplicates.
- Asks the small model for at most two sentences and 45 words, then falls back to a plan-derived sentence when generation fails or returns empty.
- Bounds every field before dispatch: title 120 chars, reason 500, description 280. Context is compacted to lead name, email, company, status, and three truncated RAG excerpts.
- Always dispatches `create_task` with `requires_approval=True`, assigned to the event actor when present.

Where
- [../app/workflows/lead_nudge.py](../app/workflows/lead_nudge.py), [../app/prompts/workflows/lead_nudge.md](../app/prompts/workflows/lead_nudge.md)

### 15.2 Deal risk (`deal_risk`)

Why
- A manager needs early warning on stalling deals, but an informational alert should not sit behind an approval queue.

How
- Uses the large model tier, since risk assessment needs more reasoning than a follow-up line.
- Falls back to a fixed message when generation fails. Bounds title to 120, reason to 500, message to 260 characters.
- Compacts context to stage, status, value, currency, expected close date, and three RAG excerpts.
- Dispatches `create_alert` with `requires_approval=False`, addressed to the plan's recipient or the actor.

Where
- [../app/workflows/deal_risk.py](../app/workflows/deal_risk.py), [../app/prompts/workflows/deal_risk.md](../app/prompts/workflows/deal_risk.md)

### 15.3 Daily summary (`daily_summary`)

Why
- Reps start the day needing one consolidated view of their pipeline instead of five list pages.

How
- Runs on the daily-summary context path (owned leads, owned deals, tasks, owner-scoped RAG).
- Generates with the small model, falls back to a fixed line, then passes the result through `format_daily_summary`, which strips markdown headings, emoji, bullet markers, and horizontal rules, and re-splits AI blobs that used spaced dashes or numbered chains as pseudo-bullets.
- Dispatches the planner's action type (normally `create_note`) with the formatted summary as content.

Where
- [../app/workflows/daily_summary.py](../app/workflows/daily_summary.py), [../app/services/content_formatter.py](../app/services/content_formatter.py), [../app/prompts/workflows/daily_summary.md](../app/prompts/workflows/daily_summary.md)

### 15.4 Task auto-creation (`task_auto`)

Why
- Playbook next-steps should be proposed automatically rather than remembered by each rep.

How
- Skips the planner entirely and generates a description directly from the `task_auto` workflow prompt, with a fixed fallback.
- Dispatches `create_task`; `ActionManager` forces approval because `create_task` is in the high-risk set.

Where
- [../app/workflows/task_auto.py](../app/workflows/task_auto.py), [../app/prompts/workflows/task_auto.md](../app/prompts/workflows/task_auto.md)

### 15.5 Task deadline watch (`task_deadline_watch`)

Why
- Deadline severity, eligibility, and dedupe are deterministic backend rules. The model should only add a recovery suggestion where it earns its cost — high-severity, customer-facing, cache-miss cases.

How
- The only workflow that bypasses `GraphRunner`; it operates entirely on the candidate metadata the backend supplied.
- Records a `deadline_gate` trace with severity, customer-facing flag, LLM decision, and cache-hit state, then exits early if `should_use_llm` is false or a fresh LLM output already exists.
- On generation failure or empty output it uses a fallback summary and flags `fallback_used`. Output is whitespace-collapsed and capped at 600 characters.
- Posts the alert back to the backend's deadline-alerts endpoint with the cache key, then dispatches an internal `create_note` with `requires_approval=False`.
- The note's idempotency key is `tdn:{entity_id}:{context_hash}` — the backend caps `idempotency_key` at 64 characters, and embedding the full `llm_cache_key` produced ~130 characters and a 422. The context hash already encodes task identity, severity, and content, so the semantics are preserved.

Where
- [../app/workflows/task_deadline_watch.py](../app/workflows/task_deadline_watch.py), [../app/prompts/workflows/task_deadline_watch.md](../app/prompts/workflows/task_deadline_watch.md)

### 15.6 Meeting intelligence (`meeting_complete`)

Why
- Meeting recordings contain commitments that never reach the CRM, but a mic test or small talk must not become a fabricated task.

How
- A keyword gate runs before the model: a transcript under 40 characters, or one with none of ~30 action cues ("follow up", "schedule", "i'll", "by monday", …), returns no action and never reaches the LLM.
- Uses the large tier and demands strict JSON (`title`, `task_description`, `due_at`, `priority`, `note_content`) with an explicit instruction to return `NO_ACTION_ITEMS` rather than invent a task. The current date is injected so relative deadlines resolve.
- Response parsing is defensive: `NO_ACTION_ITEMS` and its variants map to no action, fenced code blocks are stripped, and non-JSON text degrades into a single-task payload rather than failing. Priority is clamped to low/medium/high; title is capped at 120 characters and description at 240.
- Verbose detail is routed to `note_content` so the task description stays card-sized.
- Dispatches `create_task` with `requires_approval=True`.

Where
- [../app/workflows/meeting_intel.py](../app/workflows/meeting_intel.py), [../app/prompts/workflows/meeting_intel.md](../app/prompts/workflows/meeting_intel.md)

## 16) Meeting transcription pipeline

Why
- Transcription is slow, external, and failure-prone. It needs durable job state, bounded retries, and crash recovery — none of which fit in a request handler.

How
- The backend posts `POST /transcriptions/recording-ready` when a call recording completes. `accept_recording` upserts a job row and the route schedules processing as a FastAPI background task.
- Job state lives in `ai_meeting_transcripts` with statuses pending/processing/completed/failed, an attempt counter against `TRANSCRIPTION_MAX_ATTEMPTS`, and retry/timeout timestamps.
- `_start_attempt` is a conditional `UPDATE ... RETURNING` — the attempt counter increments and the status flips to processing in one atomic statement, so two concurrent callers cannot both claim the same job.
- Path resolution is sandboxed: a recording path is resolved against the configured recordings directory and rejected unless `_is_within` confirms it stays inside that base, which blocks traversal out of the shared recordings volume.
- AssemblyAI runs in a worker thread via `asyncio.to_thread`. The configured speech-model fallback list is passed when the installed SDK supports it, and a `TypeError` falls back to language-only config rather than failing.
- On success the transcript and a generated 2–4 sentence meeting summary are stored, the backend call session is updated, and `_trigger_meeting_intel` fires a `meeting_complete` event into the orchestrator.
- Crash recovery: any job sitting in `processing` beyond `TRANSCRIPTION_PROCESSING_TIMEOUT_MINUTES` is swept back to pending (or failed if attempts are exhausted) and re-queued, both on demand and by a scheduled job.
- Schema DDL is gated — `ensure_schema` only runs in dev; production relies on migration `0007`.

Where
- Transcription service: [../app/services/transcription_service.py](../app/services/transcription_service.py)
- Callback routes: [../app/api/routes/transcriptions.py](../app/api/routes/transcriptions.py)
- Job schemas: [../app/schemas/transcriptions.py](../app/schemas/transcriptions.py)
- Table migration: [../alembic/versions/0007_add_ai_meeting_transcripts.py](../alembic/versions/0007_add_ai_meeting_transcripts.py)

## 17) Scheduler and background jobs

Why
- Most agent value is proactive. Nothing in the CRM UI triggers a stale-lead scan.

How
- APScheduler `AsyncIOScheduler`, registered only when `SCHEDULER_ENABLED=true` and the backend heartbeat succeeded.
- Jobs: `daily_summary` (cron, default 08:00), `lead_score_sweep` (interval, 6h), `stale_lead` (6h), `deal_risk` (6h), `task_deadline_watch` (interval, minimum 15 min), `rag_sync` (interval, `RAG_SYNC_INTERVAL_HOURS`, only when enabled, `max_instances=1` and `coalesce=True` so a slow sync cannot stack), `transcription_stale_sweep` (30 min), and `trace_retention_sweep` (cron, 00:30).
- Interval jobs clamp to sane minimums (`max(1, hours)`, `max(15, minutes)`) so a misconfigured value cannot produce a hot loop.
- Candidate-driven jobs fetch a bounded list from the backend (`SCHEDULER_*_CANDIDATE_LIMIT`, default 500 / 100) and emit one event per candidate into the orchestrator, where per-entity idempotency prevents duplicate runs.
- The deadline job first asks the backend to run its deterministic rule sweep, then only forwards candidates where `should_use_llm` is true and no fresh output is cached.
- Every job body is wrapped in try/except and logs the exception; one failing job never stops the scheduler.

Where
- Job definitions and registration: [../app/core/jobs.py](../app/core/jobs.py)
- Scheduler instance: [../app/core/scheduler.py](../app/core/scheduler.py)
- Intervals and limits: [../app/config.py](../app/config.py)

## 18) Observability

Why
- The service runs unattended, so failures must be visible without a user reporting them.

How
- In-process metrics only — thread-safe `Counter`, `Histogram`, and `Gauge` classes with label support and no Prometheus dependency, exposed as JSON at `GET /metrics`.
- Tracked: `planner_retries_total` (by provider and category), `planner_failures_total`, `content_generation_failures_total`, `llm_request_latency_ms` (by provider and workflow), `approval_requests_total`, `circuit_breaker_trips_total`, and `circuit_breaker_state`.
- Every log record carries `cid=` (correlation ID) and `rid=` (run ID) via a logging filter reading context vars, so one event's logs can be reconstructed across async boundaries.
- `GET /health/config` reports which providers are configured without leaking values.
- `GET /health/ready` exposes the full readiness snapshot: backend connected, database connected, scheduler started, reason, and timestamp.

Where
- Metrics primitives and registry: [../app/core/metrics.py](../app/core/metrics.py)
- Metrics endpoint: [../app/api/routes/metrics.py](../app/api/routes/metrics.py)
- Correlated logging: [../app/core/logging.py](../app/core/logging.py), [../app/core/correlation.py](../app/core/correlation.py)

## 19) Database and migrations

Why
- The service owns only what the backend cannot: durable transcription job state and, optionally, the pgvector index.

How
- An asyncpg pool is created at startup from `DATABASE_URL` and closed on shutdown. `get_pool()` raises if called before initialization. When `DATABASE_URL` is unset no pool is created — which is why memory/FAISS vector stores and a no-DB dev run remain possible.
- Alembic migrations run 0001 → 0007: create agent tables, enable RLS, rename `agent_*` to `ai_*`, add `ai_run_traces`, add `ai_context_chunks`, harden context and trace RLS, add `ai_meeting_transcripts`.
- SQLAlchemy models exist for `ai_runs`, `ai_actions`, and `ai_approval_requests` and back the Alembic autogenerate target. At runtime the backend owns these rows — the service reads and writes them through the control-plane API, not through these models.
- `AgentStore` holds raw asyncpg statements for the same tables; it is the local-persistence path, retained but not on the primary control-plane flow.

Where
- Pool: [../app/db/pool.py](../app/db/pool.py)
- Models: [../app/db/models.py](../app/db/models.py)
- Local store: [../app/db/agent_store.py](../app/db/agent_store.py)
- Migrations: [../alembic/versions](../alembic/versions)

## 20) Configuration

Why
- Every external dependency, interval, and limit should be tunable per environment without a code change.

How
- Pydantic `BaseSettings` loads `.env` from the service root, case-insensitive, ignoring unknown keys. Most fields use `AliasChoices` so historical env var names keep working (`AUTOCRM_BASE_URL`/`AUTOCRM_BACKEND_URL`; the recordings directory accepts four aliases shared with the backend).
- Computed helpers keep environment logic in one place: `is_dev` (explicit `DEV_MODE` overrides `APP_ENV`), `should_ensure_transcription_schema`, `retry_policy_for(provider)`, and `circuit_breaker_config_for(provider)`.
- `ASSEMBLYAI_SPEECH_MODELS` is stored as a comma-separated string rather than a list, because pydantic-settings would otherwise JSON-decode a `list[str]` env value; the `assemblyai_speech_models` property parses it into the ordered fallback list.
- Requires Python 3.11 or 3.12 — on 3.13 numpy builds from source and fails on Windows.

Where
- Settings: [../app/config.py](../app/config.py)
- Template: [../.env.example](../.env.example)
- Setup and env var groups: [../README.md](../README.md)

## 21) Tests

Why
- The security and resilience behavior above is invisible at runtime until it fails, so it is pinned by tests.

How
- Pytest suite covering the action manager, action policy, agent loop, orchestrator, circuit breaker, context service, embeddings, planner, RAG, RAG sync, retry, migration security (RLS), startup security, trace redaction, and an end-to-end workflow path.

Where
- Tests: [../tests](../tests)

## 22) Known placeholders and current limits

Why
- Document the current implementation boundaries so they are not mistaken for finished behavior.

How
- The default `VECTOR_STORE` is `memory`, which is process-local and lost on restart; `.env.example` sets `faiss` for real use, and `pgvector` is the multi-instance option.
- FAISS persistence rebuilds and re-pickles the whole index on every mutation, so index writes are O(n) in indexed chunks — acceptable at current volume, not at large scale.
- Metrics, the circuit breaker registry, and the transcription schema flag are all in-process, so values are per worker rather than global. A shared store would be needed for a multi-instance deployment.
- The local `EmbeddingService` is a deterministic hashing embedder, not a semantic model. It keeps RAG operational offline but retrieval quality is far below the sentence-transformers provider.
- `app/db/session.py` is a placeholder holding only a `get_database_url()` helper.
- The RAG sync cursor is a local JSON file, which does not survive an ephemeral filesystem.
- Disabled lazy config guards remain as commented reference blocks in the LLM, embedding, and transcription services; the live checks are in `startup_checks.py`.

Where
- Vector store defaults: [../app/config.py](../app/config.py), [../app/services/vector_store.py](../app/services/vector_store.py)
- Local embedder: [../app/services/embedding_service.py](../app/services/embedding_service.py)
- Session placeholder: [../app/db/session.py](../app/db/session.py)
- Sync state file: [../app/services/rag_sync_service.py](../app/services/rag_sync_service.py)
- Startup checks: [../app/core/startup_checks.py](../app/core/startup_checks.py)
