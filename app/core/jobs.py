from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.config import settings
from app.core.scheduler import scheduler
from app.schemas.events import AgentEventIn
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.autocrm_client import AutoCRMClient
from app.services.rag_sync_service import RagSyncService
from app.services.transcription_service import TranscriptionService


logger = logging.getLogger(__name__)


def _parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def register_jobs(scheduler_instance) -> None:
    scheduler_instance.add_job(
        _run_daily_summaries,
        "cron",
        hour=settings.scheduler_daily_summary_hour,
        minute=settings.scheduler_daily_summary_minute,
    )
    scheduler_instance.add_job(
        _run_lead_score_sweep,
        "interval",
        hours=max(1, settings.scheduler_lead_score_sweep_interval_hours),
    )
    scheduler_instance.add_job(
        _run_stale_leads,
        "interval",
        hours=max(1, settings.scheduler_stale_lead_sweep_interval_hours),
    )
    scheduler_instance.add_job(
        _run_deal_risks,
        "interval",
        hours=max(1, settings.scheduler_deal_risk_sweep_interval_hours),
    )
    scheduler_instance.add_job(
        _run_task_deadline_watch,
        "interval",
        minutes=max(15, settings.scheduler_task_deadline_sweep_interval_minutes),
    )
    if settings.rag_sync_enabled:
        scheduler_instance.add_job(
            _run_rag_sync,
            "interval",
            hours=max(1, settings.rag_sync_interval_hours),
            max_instances=1,
            coalesce=True,
        )
    scheduler_instance.add_job(
        _run_transcription_stale_sweep,
        "interval",
        minutes=max(1, settings.transcription_stale_sweep_interval_minutes),
    )
    # Issue #6 — scheduled trace retention sweep
    scheduler_instance.add_job(
        _run_trace_retention_sweep,
        "cron",
        hour=0,
        minute=30,
    )


def _run_coroutine(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    loop.create_task(coro)


def run_daily_summaries() -> None:
    _run_coroutine(_run_daily_summaries())


def run_stale_leads() -> None:
    _run_coroutine(_run_stale_leads())


def run_lead_score_sweep() -> None:
    _run_coroutine(_run_lead_score_sweep())


def run_deal_risks() -> None:
    _run_coroutine(_run_deal_risks())


def run_task_deadline_watch() -> None:
    _run_coroutine(_run_task_deadline_watch())


def run_transcription_stale_sweep() -> None:
    _run_coroutine(_run_transcription_stale_sweep())


def run_rag_sync() -> None:
    _run_coroutine(_run_rag_sync())


async def _run_daily_summaries() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    users = await client.list_summary_candidates(limit=settings.scheduler_summary_candidate_limit)
    for user in users:
        user_id = _parse_uuid(user.get("id"))
        if user_id is None:
            continue
        payload = AgentEventIn(
            event_type="daily_summary",
            entity_id=user_id,
            entity_type="user",
            actor_id=str(user_id),
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_stale_leads() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    leads = await client.list_stale_lead_candidates(limit=settings.scheduler_stale_lead_candidate_limit)
    for lead in leads:
        lead_id = _parse_uuid(lead.get("id"))
        if lead_id is None:
            continue
        payload = AgentEventIn(
            event_type="stale_lead",
            entity_id=lead_id,
            entity_type="lead",
            actor_id=str(lead.get("owner_id") or ""),
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_lead_score_sweep() -> None:
    try:
        result = await AutoCRMClient().sweep_lead_scores(limit=100)
        logger.info("lead_score_sweep_queued result=%s", result)
    except Exception:
        logger.exception("lead_score_sweep_failed")


async def _run_deal_risks() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    deals = await client.list_deal_risk_candidates(limit=settings.scheduler_deal_risk_candidate_limit)
    for deal in deals:
        deal_id = _parse_uuid(deal.get("id"))
        if deal_id is None:
            continue
        payload = AgentEventIn(
            event_type="deal_risk",
            entity_id=deal_id,
            entity_type="deal",
            actor_id=str(deal.get("owner_id") or ""),
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_task_deadline_watch() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    try:
        result = await client.run_task_deadline_sweep(limit=settings.scheduler_task_deadline_candidate_limit)
        logger.info("task_deadline_rule_sweep result=%s", result)
    except Exception:
        logger.exception("task_deadline_rule_sweep_failed")

    candidates = await client.list_task_deadline_candidates(limit=settings.scheduler_task_deadline_candidate_limit)
    for candidate in candidates:
        if not candidate.get("should_use_llm") or candidate.get("fresh_llm_output"):
            continue
        task_id = _parse_uuid(candidate.get("task_id"))
        if task_id is None:
            continue
        payload = AgentEventIn(
            event_type="task_deadline_watch",
            entity_id=task_id,
            entity_type="task",
            actor_id=str(candidate.get("assigned_to") or candidate.get("owner_id") or ""),
            metadata={**candidate, "source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_transcription_stale_sweep() -> None:
    try:
        recovered = await TranscriptionService().sweep_stale_processing_jobs()
        if recovered:
            logger.info("transcription_stale_sweep_recovered count=%s", recovered)
    except asyncio.CancelledError:
        logger.info("transcription_stale_sweep_cancelled")
    except Exception:
        logger.exception("transcription_stale_sweep_failed")


async def _run_rag_sync() -> None:
    try:
        indexed = await RagSyncService().run_once()
        if indexed:
            logger.info("rag_sync_completed indexed=%s", indexed)
    except Exception:
        logger.exception("rag_sync_failed")


async def _run_trace_retention_sweep() -> None:
    """Delete ai_run_traces older than the configured retention period (Issue #6)."""
    from app.db.pool import get_pool

    retention_days = settings.ai_trace_retention_days
    try:
        pool = get_pool()
        result = await pool.execute(
            """
            DELETE FROM ai_run_traces
            WHERE created_at < NOW() - ($1::int * INTERVAL '1 day')
            """,
            retention_days,
        )
        logger.info("trace_retention_sweep_completed retention_days=%d result=%s", retention_days, result)
    except Exception:
        logger.exception("trace_retention_sweep_failed")
