"""Tests for app.core.circuit_breaker — state transitions and CircuitOpenError."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    get_breaker,
    reset_all_breakers,
)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_all_breakers()
    yield
    reset_all_breakers()


class TestCircuitBreakerStates:
    async def test_starts_closed(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3, reset_timeout_seconds=1.0))
        assert cb.state == CircuitBreaker.CLOSED

    async def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3, reset_timeout_seconds=1.0))
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        await cb.check()  # should not raise

    async def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3, reset_timeout_seconds=1.0))
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    async def test_open_raises_circuit_open_error(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, reset_timeout_seconds=100.0))
        await cb.record_failure()
        await cb.record_failure()
        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.check()
        assert "test" in str(exc_info.value)

    async def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0.05))
        await cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        await asyncio.sleep(0.1)
        await cb.check()  # should transition to half_open
        assert cb.state == CircuitBreaker.HALF_OPEN

    async def test_half_open_success_closes(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0.05))
        await cb.record_failure()
        await asyncio.sleep(0.1)
        await cb.check()  # half_open
        await cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    async def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0.05))
        await cb.record_failure()
        await asyncio.sleep(0.1)
        await cb.check()  # half_open
        await cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3, reset_timeout_seconds=1.0))
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()  # resets
        await cb.record_failure()
        await cb.record_failure()
        # Should still be closed (only 2 consecutive failures after reset)
        assert cb.state == CircuitBreaker.CLOSED


class TestCircuitBreakerRegistry:
    async def test_get_breaker_returns_same_instance(self):
        b1 = await get_breaker("ollama")
        b2 = await get_breaker("ollama")
        assert b1 is b2

    async def test_get_breaker_different_providers(self):
        b1 = await get_breaker("ollama")
        b2 = await get_breaker("openai")
        assert b1 is not b2

    def test_circuit_open_error_attributes(self):
        exc = CircuitOpenError("test_provider")
        assert exc.provider == "test_provider"
        assert "test_provider" in str(exc)
