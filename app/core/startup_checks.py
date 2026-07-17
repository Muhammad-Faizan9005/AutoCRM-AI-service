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


async def verify_security_config() -> None:
    """Fail-fast if the webhook token is missing outside development.

    Called from ``main.py`` lifespan — aborting startup is consistent with
    how ``verify_backend_connectivity`` already raises on missing config.
    """
    if not settings.is_dev and not settings.ai_service_webhook_token:
        raise RuntimeError(
            "AI_SERVICE_WEBHOOK_TOKEN is required outside development. "
            "Set the environment variable or use DEV_MODE=true / APP_ENV=development."
        )
