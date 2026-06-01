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

## LangGraph + RAG
Workflows are executed using a simple LangGraph pipeline that gathers context
and dispatches actions. RAG is an in-memory placeholder and should be swapped
for FAISS or Pinecone when available.
