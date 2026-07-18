from __future__ import annotations

import logging
import time

import httpx

from app.config import settings
from app.core.circuit_breaker import get_breaker
from app.core.metrics import (
    llm_request_latency_ms,
    planner_retries_total,
)
from app.core.retry import RetryPolicy, classify_failure, is_retryable, retry_async
from app.prompts import load_prompt

logger = logging.getLogger(__name__)


class LLMService:
    async def generate(
        self,
        *,
        prompt: str,
        model_tier: str = "small",
        workflow: str | None = None,
        context: str = "",
        json_mode: bool = False,
        correlation_id: str = "",
    ) -> str:
        if not settings.llm_enabled:
            return ""

        # Compose full prompt with guardrails if workflow is provided
        if workflow:
            prompt = load_prompt(workflow, context or prompt)

        provider = settings.llm_provider.strip().lower()
        if provider == "ollama":
            model = self._resolve_model(model_tier)
            return await self._generate_with_resilience(
                provider, model, prompt, json_mode=json_mode, workflow=workflow
            )
        if provider == "openai":
            model = self._resolve_model(model_tier)
            return await self._generate_with_resilience(
                provider, model, prompt, json_mode=json_mode, workflow=workflow
            )
        raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")

    async def _generate_with_resilience(
        self,
        provider: str,
        model: str,
        prompt: str,
        *,
        json_mode: bool = False,
        workflow: str | None = None,
    ) -> str:
        """Run the LLM call through circuit breaker + retry_async with latency tracking."""
        # 1. Check circuit breaker
        cb_config = settings.circuit_breaker_config_for(provider)
        breaker = await get_breaker(provider, cb_config)
        await breaker.check()  # raises CircuitOpenError if open

        # 2. Resolve retry policy
        policy = settings.retry_policy_for(provider)

        # 3. Define the callable for retry_async
        if provider == "ollama":
            call_fn = lambda: self._generate_ollama(prompt, model, json_mode=json_mode)
        else:
            call_fn = lambda: self._generate_openai(prompt, model, json_mode=json_mode)

        # 4. on_retry callback — emit metrics
        def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            category = classify_failure(exc)
            planner_retries_total.inc(provider=provider, category=category)
            logger.warning(
                "llm_retry provider=%s attempt=%d delay=%.2fs category=%s error=%s",
                provider, attempt, delay, category, exc,
            )

        # 5. Execute with retry + latency tracking
        start = time.perf_counter()
        try:
            result = await retry_async(
                call_fn,
                policy=policy,
                is_retryable=lambda exc: is_retryable(exc, policy=policy),
                on_retry=on_retry,
            )
            await breaker.record_success()
            return result
        except Exception as exc:
            await breaker.record_failure()
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            llm_request_latency_ms.observe(
                elapsed_ms, provider=provider, workflow=workflow or "unknown"
            )

    async def _generate_ollama(self, prompt: str, model: str, *, json_mode: bool = False) -> str:
        url = f"{settings.ollama_base_url}/api/generate"
        options: dict = {
            "temperature": 0.2,
            "num_predict": 700,
        }
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data.get("response") or "")

    async def _generate_openai(self, prompt: str, model: str, *, json_mode: bool = False) -> str:
        # -------------------------------------------------------------------
        # DISABLED (2026-07-18): mid-request OPENAI_API_KEY config check.
        # What it was: a lazy guard that raised only on the first OpenAI call
        #   if the key was unset.
        # Why disabled: config should fail fast at boot. This is now validated
        #   at startup by `verify_provider_config()` (app/core/startup_checks.py)
        #   whenever LLM_PROVIDER=openai — aborts in prod, warns in dev.
        # Kept commented (not deleted) as reference / fallback.
        #
        # if not settings.openai_api_key:
        #     raise RuntimeError("OPENAI_API_KEY is not configured")
        # -------------------------------------------------------------------
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 700,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            message = choices[0].get("message") or {}
            return str(message.get("content") or "")

    def _resolve_model(self, model_tier: str) -> str:
        tier = model_tier.strip().lower()
        if tier == "large":
            return settings.llm_model_large
        return settings.llm_model_small
