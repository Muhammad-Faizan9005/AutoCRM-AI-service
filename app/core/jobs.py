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
    scheduler_instance.add_job(_run_daily_summaries, "cron", hour=8, minute=0)
    scheduler_instance.add_job(_run_lead_score_sweep, "interval", hours=1)
    scheduler_instance.add_job(_run_stale_leads, "interval", hours=6)
    scheduler_instance.add_job(_run_deal_risks, "interval", hours=1)
    if settings.rag_sync_enabled:
        scheduler_instance.add_job(
            _run_rag_sync,
            "interval",
            seconds=max(30, settings.rag_sync_interval_seconds),
            max_instances=1,
            coalesce=True,
        )
    scheduler_instance.add_job(
        _run_transcription_stale_sweep,
        "interval",
        minutes=max(1, settings.transcription_stale_sweep_interval_minutes),
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


def run_transcription_stale_sweep() -> None:
    _run_coroutine(_run_transcription_stale_sweep())


def run_rag_sync() -> None:
    _run_coroutine(_run_rag_sync())


async def _run_daily_summaries() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    users = await client.list_summary_candidates()
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
    leads = await client.list_stale_lead_candidates()
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
    deals = await client.list_deal_risk_candidates()
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
