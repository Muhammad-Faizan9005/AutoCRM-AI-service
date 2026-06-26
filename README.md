# AutoCRM AI Agent Service

Independent agent service for AutoCRM that runs proactive workflows and calls back into AutoCRM via authenticated APIs.

## Stack
- FastAPI
- LangGraph + LangChain
- APScheduler

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

## Workflows (v1)
- Lead follow-up nudges
- Deal risk alerts
- Task auto-creation
- Daily summaries
- Meeting intelligence (transcribe -> summarize -> action items)

## Scheduler
The service registers APScheduler jobs for:
- `daily_summary` (cron at 08:00)
- `stale_lead` (every 6 hours)
- `deal_risk` (hourly)

Jobs emit events into the orchestrator. Update intervals in `app/core/jobs.py`.

## Control Plane
The AutoCRM backend is the source of truth for agent runs, traces, actions,
approvals, and CRM records. The AI service creates backend runs with stable
external IDs, records traces through backend APIs, and dispatches proposed
actions to `/api/agent/actions` so approval and CRM writes stay centralized.

## LangGraph + RAG
Workflows are executed using a LangGraph pipeline that gathers context and
dispatches actions. RAG uses a persistent FAISS index by default and syncs CRM
documents from the backend in throttled background batches. Configure
`VECTOR_STORE=faiss`, `RAG_INDEX_DIR`, `RAG_SYNC_INTERVAL_SECONDS`, and
`RAG_SYNC_BATCH_SIZE` in `.env`.

## Ollama
Set `LLM_PROVIDER=ollama`, `LLM_MODEL_SMALL=gemma2:2b`, and
`LLM_MODEL_LARGE=glm-4.6:cloud` in `.env`. Make sure
Ollama is running at `OLLAMA_BASE_URL`.

Model install:
```
ollama pull gemma2:2b
ollama pull glm-4.6:cloud
```
