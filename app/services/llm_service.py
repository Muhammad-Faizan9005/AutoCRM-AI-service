from __future__ import annotations

import httpx

from app.config import settings
from app.prompts import load_prompt


class LLMService:
    async def generate(self, *, prompt: str, model_tier: str = "small", workflow: str | None = None, context: str = "") -> str:
        if not settings.llm_enabled:
            return ""

        # Compose full prompt with guardrails if workflow is provided
        if workflow:
            prompt = load_prompt(workflow, context or prompt)

        provider = settings.llm_provider.strip().lower()
        if provider == "ollama":
            model = self._resolve_model(model_tier)
            return await self._generate_ollama(prompt, model)
        if provider == "openai":
            model = self._resolve_model(model_tier)
            return await self._generate_openai(prompt, model)
        raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")

    async def _generate_ollama(self, prompt: str, model: str) -> str:
        url = f"{settings.ollama_base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 700,
            },
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data.get("response") or "")

    async def _generate_openai(self, prompt: str, model: str) -> str:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 700,
        }
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
