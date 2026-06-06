from __future__ import annotations

import asyncio

import pytest

from app.services import embedding_service as embedding_module
from app.services.embedding_service import (
    EmbeddingService,
    HuggingFaceEmbeddingService,
    build_embedding_service,
)


def test_huggingface_embedding_service_mean_pools_token_vectors() -> None:
    service = HuggingFaceEmbeddingService(
        api_token="token",
        model="sentence-transformers/all-MiniLM-L6-v2",
        base_url="https://example.test",
    )

    vector = service._mean_pool([[[1.0, 3.0], [3.0, 5.0]]])

    assert vector == [2.0, 4.0]


def test_huggingface_embedding_service_requires_token() -> None:
    service = HuggingFaceEmbeddingService(
        api_token="",
        model="sentence-transformers/all-MiniLM-L6-v2",
        base_url="https://example.test",
    )

    with pytest.raises(RuntimeError, match="HUGGINGFACE_API_TOKEN"):
        asyncio.run(service.embed("hello"))


def test_build_embedding_service_uses_huggingface_provider(monkeypatch) -> None:
    monkeypatch.setattr(embedding_module.settings, "embedding_provider", "huggingface")
    monkeypatch.setattr(embedding_module.settings, "huggingface_api_token", "token")

    service = build_embedding_service()

    assert isinstance(service, HuggingFaceEmbeddingService)


def test_build_embedding_service_defaults_to_local(monkeypatch) -> None:
    monkeypatch.setattr(embedding_module.settings, "embedding_provider", "local")

    service = build_embedding_service()

    assert isinstance(service, EmbeddingService)
