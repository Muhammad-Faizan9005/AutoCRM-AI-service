from __future__ import annotations

import hashlib
import math
import re
import asyncio
import threading

from app.config import settings


_MODEL_CACHE: dict[tuple[str, str], object] = {}
_MODEL_CACHE_LOCK = threading.Lock()


class EmbeddingService:
    """
    Deterministic local embeddings for development and tests.

    This keeps the RAG pipeline operational without a network dependency. The
    vector-store interface can use provider embeddings later without changing
    retrieval callers.
    """

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return self._normalize(vector)

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def _normalize(self, vector: list[float]) -> list[float]:
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


class HuggingFaceEmbeddingService:
    def __init__(
        self,
        *,
        api_token: str,
        model: str,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.api_token = api_token
        self.model = model
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self._model = None

    async def embed(self, text: str) -> list[float]:
        # -------------------------------------------------------------------
        # DISABLED (2026-07-18): mid-request HUGGINGFACE_API_TOKEN config check.
        # What it was: a lazy guard that raised only on the first embed() call
        #   if the token was unset.
        # Why disabled: config should fail fast at boot. This is now validated
        #   at startup by `verify_provider_config()` (app/core/startup_checks.py)
        #   whenever EMBEDDING_PROVIDER=huggingface — aborts in prod, warns in dev.
        # Kept commented (not deleted) as reference / fallback.
        #
        # if not self.api_token:
        #     raise RuntimeError("HUGGINGFACE_API_TOKEN is required for Hugging Face embeddings")
        # -------------------------------------------------------------------
        model = await asyncio.to_thread(self._load_model)
        embedding = await asyncio.to_thread(
            model.encode,
            text,
            normalize_embeddings=True,
        )
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        return self._normalize([float(value) for value in embedding])

    def _load_model(self):
        if self._model is not None:
            return self._model
        cache_key = (self.model, self.api_token)
        cached_model = _MODEL_CACHE.get(cache_key)
        if cached_model is not None:
            self._model = cached_model
            return cached_model

        with _MODEL_CACHE_LOCK:
            cached_model = _MODEL_CACHE.get(cache_key)
            if cached_model is not None:
                self._model = cached_model
                return cached_model

            model = self._build_model()
            _MODEL_CACHE[cache_key] = model
            self._model = model
            return model

    def _build_model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for Hugging Face embeddings. "
                "Install AI service requirements first."
            ) from exc

        return SentenceTransformer(self.model, token=self.api_token)

    def _mean_pool(self, data: object) -> list[float]:
        if self._is_vector(data):
            return [float(value) for value in data]
        if isinstance(data, list) and data and self._is_vector(data[0]):
            return [float(value) for value in data[0]]
        if isinstance(data, list) and data and isinstance(data[0], list) and data[0] and self._is_vector(data[0][0]):
            token_vectors = data[0]
            dimensions = len(token_vectors[0])
            pooled = [0.0] * dimensions
            for vector in token_vectors:
                for index, value in enumerate(vector):
                    pooled[index] += float(value)
            return [value / len(token_vectors) for value in pooled]
        raise ValueError("Unexpected Hugging Face embedding response shape")

    def _is_vector(self, value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, int | float) for item in value)

    def _normalize(self, vector: list[float]) -> list[float]:
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


def build_embedding_service():
    provider = settings.embedding_provider.strip().lower()
    if provider in {"huggingface", "hf"}:
        return HuggingFaceEmbeddingService(
            api_token=settings.huggingface_api_token,
            model=settings.huggingface_embedding_model,
            base_url=settings.huggingface_api_base_url,
        )
    return EmbeddingService(dimensions=settings.embedding_dimensions)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))
