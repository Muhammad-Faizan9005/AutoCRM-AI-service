from __future__ import annotations

import httpx

from app.config import settings


class LLMService:
    async def generate(self, *, prompt: str, model_tier: str = "small") -> str:
        if not settings.llm_enabled:
            return ""

        provider = settings.llm_provider.strip().lower()
        if provider == "ollama":
            model = self._resolve_model(model_tier)
            return await self._generate_ollama(prompt, model)
        if provider == "openai":
            return ""
        return ""

    async def _generate_ollama(self, prompt: str, model: str) -> str:
        url = f"{settings.ollama_base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data.get("response") or "")

    def _resolve_model(self, model_tier: str) -> str:
        tier = model_tier.strip().lower()
        if tier == "large":
            return settings.llm_model_large
        return settings.llm_model_small
