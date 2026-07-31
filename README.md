# AutoCRM AI Agent Service

Independent agent service for AutoCRM that runs proactive workflows and calls back into AutoCRM via authenticated APIs.

## Stack
- FastAPI + Uvicorn
- LangGraph + LangChain
- APScheduler (async background jobs)
- PostgreSQL via asyncpg / SQLAlchemy, migrated with Alembic
- FAISS + sentence-transformers / Hugging Face embeddings for RAG
- AssemblyAI for meeting transcription

## Python Version
Use Python 3.11 or 3.12. Python 3.13 will try to build numpy from source and fails on Windows.

## Quickstart
1. Create a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill values.
4. Create the database schema with Alembic:
	- `alembic upgrade head`
5. Run the service: `uvicorn app.main:app --reload --port 8001`.

## Environment Variables
See `.env.example` for required settings.

Key groups:
- Backend API: `AUTOCRM_BASE_URL` (alias `AUTOCRM_BACKEND_URL`), `AUTOCRM_AI_AGENT_KEY`, and `AUTOCRM_AI_SERVICE_TOKEN`
- Protected callbacks: `AI_SERVICE_WEBHOOK_TOKEN`
- Database: `DATABASE_URL` (PostgreSQL, used by Alembic and the async pool)
- LLM provider: `LLM_PROVIDER`, `LLM_MODEL_SMALL`, `LLM_MODEL_LARGE`, `OLLAMA_BASE_URL`, and optionally `OPENAI_API_KEY`
- LLM resilience: per-provider `LLM_RETRY__*` and `CIRCUIT_BREAKER__*` overrides (see `app/config.py`)
- RAG storage: `VECTOR_STORE`, `RAG_INDEX_DIR`, `RAG_SYNC_ENABLED`, `RAG_SYNC_INTERVAL_HOURS`, and `RAG_SYNC_BATCH_SIZE`
- Embeddings: `EMBEDDING_PROVIDER`, `EMBEDDING_DIMENSIONS`, `HUGGINGFACE_EMBEDDING_MODEL`, and `HUGGINGFACE_API_TOKEN`
- Transcriptions: `TRANSCRIPTION_RECORDINGS_DIR`, `ASSEMBLYAI_API_KEY`, `ASSEMBLYAI_SPEECH_MODELS`, and `ASSEMBLYAI_LANGUAGE_CODE`
- Scheduler: `SCHEDULER_ENABLED` plus per-job interval/limit overrides (see `app/config.py`)
- Trace retention: `AI_TRACE_RETENTION_DAYS`

Keep real values in `.env` or a secret manager only. Do not commit live DB, backend, AI-service, JWT, provider, or service-account secrets.

## API Security

- `GET /health` and `GET /health/ready` are lightweight public liveness/readiness endpoints.
- All operational endpoints require `X-AutoCRM-AI-Webhook-Token` when `AI_SERVICE_WEBHOOK_TOKEN` is configured (bypassed only in `development`/`test`):
  - `POST /agent/events` — ingest an event and dispatch a workflow run.
  - `GET /agent/runs/{run_id}` and `GET /agent/runs/{run_id}/trace` — run status and traces (read from backend).
  - `POST /transcriptions/recording-ready`, `GET /transcriptions/{recording_id}`, `POST /transcriptions/{recording_id}/retry`, `POST /transcriptions/sweep-stale` — transcription pipeline callbacks.
  - `GET /health/config` — configuration health summary.
  - `GET /metrics` — operational metrics as JSON.
- Calls from this service back into the backend use AI agent credentials when configured. The older email/password login path is retained only as a local-development fallback.
- Prompt context and transcripts are wrapped as untrusted input before LLM calls, and traces are redacted/truncated before storage.

## Workflows (v1)
- Lead follow-up nudges
- Deal risk alerts
- Task auto-creation
- Task deadline watch
- Daily summaries
- Meeting intelligence (transcribe -> summarize -> action items)

## Scheduler
When `SCHEDULER_ENABLED=true` and the backend is reachable, the service registers APScheduler jobs for:
- `daily_summary` (cron, default 08:00 — `SCHEDULER_DAILY_SUMMARY_HOUR`/`_MINUTE`)
- `lead_score_sweep` (interval, default every 6h)
- `stale_lead` (interval, default every 6h)
- `deal_risk` (interval, default every 6h)
- `task_deadline_watch` (interval, default every 60 min)
- `rag_sync` (interval, default every `RAG_SYNC_INTERVAL_HOURS`; only when `RAG_SYNC_ENABLED=true`)
- `transcription_stale_sweep` (interval, default every 30 min)
- `trace_retention_sweep` (cron, daily at 00:30)

Jobs emit events into the orchestrator or call the backend directly. Update intervals and limits in `app/config.py`.

## Control Plane
The AutoCRM backend is the source of truth for agent runs, traces, actions,
approvals, and CRM records. The AI service creates backend runs with stable
external IDs, records traces through backend APIs, and dispatches proposed
actions to `/api/agent/actions` so approval and CRM writes stay centralized.

## LangGraph + RAG
Workflows are executed using a LangGraph pipeline that gathers context and
dispatches actions. RAG uses a persistent FAISS index by default and syncs CRM
documents from the backend in throttled background batches. Configure
`VECTOR_STORE=faiss`, `RAG_INDEX_DIR`, `RAG_SYNC_INTERVAL_HOURS`, and
`RAG_SYNC_BATCH_SIZE` in `.env`.

## Ollama
Set `LLM_PROVIDER=ollama`, `LLM_MODEL_SMALL=gemma2:2b`, and
`LLM_MODEL_LARGE=glm-4.6:cloud` in `.env`. Make sure
Ollama is running at `OLLAMA_BASE_URL`.

## OpenAI
Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use the OpenAI provider. The service sends bounded JSON requests with configured model names and generation limits.
