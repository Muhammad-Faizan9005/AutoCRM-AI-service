from __future__ import annotations

import logging

from app.config import settings
from app.core import readiness
from app.services.autocrm_client import AutoCRMClient


logger = logging.getLogger(__name__)


async def verify_backend_connectivity() -> dict[str, object]:
    if not settings.autocrm_base_url:
        raise RuntimeError("AUTOCRM_BASE_URL is required")
    if not settings.autocrm_ai_service_token:
        raise RuntimeError("AUTOCRM_AI_SERVICE_TOKEN is required")

    logger.info("backend_heartbeat_check_started")
    result = await AutoCRMClient().heartbeat()
    readiness.mark_backend_connected(result)
    logger.info(
        "backend_heartbeat_ok status=%s agent_key=%s",
        result.get("status"),
        result.get("agent_key"),
    )
    return result
