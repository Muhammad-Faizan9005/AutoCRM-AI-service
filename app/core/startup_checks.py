from __future__ import annotations

import logging
import asyncio

from app.config import settings
from app.core import readiness
from app.services.autocrm_client import AutoCRMClient


logger = logging.getLogger(__name__)


async def verify_backend_connectivity() -> dict[str, object]:
    if not settings.autocrm_base_url:
        raise RuntimeError("AUTOCRM_BASE_URL is required")
    if not settings.autocrm_ai_service_token:
        raise RuntimeError("AUTOCRM_AI_SERVICE_TOKEN is required")

    attempts = max(1, settings.backend_startup_max_attempts)
    delay = max(0.25, settings.backend_startup_retry_delay_seconds)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        logger.info("backend_heartbeat_check_started attempt=%s max_attempts=%s", attempt, attempts)
        try:
            result = await AutoCRMClient().heartbeat()
            readiness.mark_backend_connected(result)
            logger.info("backend_heartbeat_ok status=%s agent_key=%s attempt=%s", result.get("status"), result.get("agent_key"), attempt)
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            wait_seconds = min(delay * (2 ** (attempt - 1)), 15.0)
            logger.warning("backend_heartbeat_retry attempt=%s wait_seconds=%.1f error=%s", attempt, wait_seconds, type(exc).__name__)
            await asyncio.sleep(wait_seconds)
    raise RuntimeError(f"AutoCRM backend did not become ready after {attempts} attempts") from last_error


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


def verify_provider_config() -> None:
    """Validate credentials for the providers/features that are actually enabled.

    Previously these checks lived deep inside the services and only fired the
    first time a job ran (e.g. AssemblyAI key was validated at line ~277 of
    ``transcription_service.py``, mid-request). Moving them here makes a
    misconfiguration surface at startup instead of silently failing a workflow
    hours later.

    Strictness follows the same convention as ``verify_security_config``: a
    missing config aborts startup in production, but only logs a warning in
    development so local runs without every provider still work.
    """
    problems: list[str] = []

    # LLM provider — only require the key for the provider that is selected.
    if settings.llm_enabled:
        provider = settings.llm_provider.strip().lower()
        if provider == "openai" and not settings.openai_api_key:
            problems.append("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        elif provider not in {"openai", "ollama"}:
            problems.append(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")

    # Embedding provider — only require the token for the selected provider.
    if settings.embedding_provider.strip().lower() == "huggingface" and not settings.huggingface_api_token:
        problems.append("HUGGINGFACE_API_TOKEN is required when EMBEDDING_PROVIDER=huggingface")

    # Transcription — AssemblyAI is always used by the transcription pipeline,
    # so validate both the key and that the SDK is importable up front.
    if not settings.assemblyai_api_key:
        problems.append("ASSEMBLYAI_API_KEY is not configured (required for the transcription pipeline)")
    else:
        try:
            import assemblyai  # noqa: F401
        except ImportError:
            problems.append("assemblyai package is not installed (run: pip install assemblyai)")

    if not problems:
        return

    detail = "; ".join(problems)
    if settings.is_dev:
        logger.warning("provider_config_incomplete (dev mode, continuing): %s", detail)
        return
    logger.error("provider_config_check_failed: %s", detail)
    raise RuntimeError(f"Provider configuration invalid: {detail}")
