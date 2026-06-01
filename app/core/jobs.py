from __future__ import annotations

import asyncio
import logging

from app.core.scheduler import scheduler
from app.schemas.events import AgentEventIn
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.autocrm_client import AutoCRMClient


logger = logging.getLogger(__name__)


def register_jobs(scheduler_instance) -> None:
    scheduler_instance.add_job(run_daily_summaries, "cron", hour=8, minute=0)
    scheduler_instance.add_job(run_stale_leads, "interval", hours=6)
    scheduler_instance.add_job(run_deal_risks, "interval", hours=1)


def run_daily_summaries() -> None:
    asyncio.create_task(_run_daily_summaries())


def run_stale_leads() -> None:
    asyncio.create_task(_run_stale_leads())


def run_deal_risks() -> None:
    asyncio.create_task(_run_deal_risks())


async def _run_daily_summaries() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    users = await client.list_users()
    for user in users:
        user_id = str(user.get("id"))
        if not user_id:
            continue
        payload = AgentEventIn(
            event_type="daily_summary",
            entity_id=user_id,
            entity_type="user",
            actor_id=user_id,
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_stale_leads() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    leads = await client.list_leads()
    for lead in leads:
        lead_id = str(lead.get("id"))
        if not lead_id:
            continue
        payload = AgentEventIn(
            event_type="stale_lead",
            entity_id=lead_id,
            entity_type="lead",
            actor_id=str(lead.get("owner_id") or ""),
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)


async def _run_deal_risks() -> None:
    client = AutoCRMClient()
    orchestrator = AgentOrchestrator()
    deals = await client.list_deals()
    for deal in deals:
        deal_id = str(deal.get("id"))
        if not deal_id:
            continue
        payload = AgentEventIn(
            event_type="deal_risk",
            entity_id=deal_id,
            entity_type="deal",
            actor_id=str(deal.get("owner_id") or ""),
            metadata={"source": "scheduler"},
        )
        await orchestrator.handle_event(payload)
