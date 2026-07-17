"""Per-provider circuit breaker protecting LLM backends from retry storms."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.core.failure import FailureCategory

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting requests."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Circuit breaker open for provider '{provider}'")


@dataclass
class CircuitBreakerConfig:
    """Per-provider circuit breaker configuration."""

    failure_threshold: int = 5
    reset_timeout_seconds: float = 30.0


class CircuitBreaker:
    """Three-state circuit breaker: closed → open → half-open → closed.

    - **closed**: requests flow; consecutive failures are counted.
    - **open**: after ``failure_threshold`` consecutive failures, all requests
      are rejected immediately with :class:`CircuitOpenError` for
      ``reset_timeout_seconds``.
    - **half-open**: after the timeout, one trial request is allowed.
      Success closes the breaker; failure re-opens it.

    All state transitions are guarded by an ``asyncio.Lock``.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, provider: str, config: CircuitBreakerConfig | None = None) -> None:
        self.provider = provider
        cfg = config or CircuitBreakerConfig()
        self.failure_threshold = cfg.failure_threshold
        self.reset_timeout = cfg.reset_timeout_seconds
        self._state = self.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def check(self) -> None:
        """Check if the breaker allows a request. Raises :class:`CircuitOpenError` if open."""
        async with self._lock:
            if self._state == self.CLOSED:
                return
            if self._state == self.OPEN:
                if time.monotonic() - self._opened_at >= self.reset_timeout:
                    self._state = self.HALF_OPEN
                    logger.info(
                        "circuit_breaker_half_open provider=%s",
                        self.provider,
                    )
                    return  # allow one trial
                raise CircuitOpenError(self.provider)
            # half_open — allow the single trial request
            return

    async def record_success(self) -> None:
        """Record a successful call — resets failure count and closes the breaker."""
        async with self._lock:
            if self._state == self.HALF_OPEN:
                logger.info(
                    "circuit_breaker_closed provider=%s (half-open trial succeeded)",
                    self.provider,
                )
            self._state = self.CLOSED
            self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed call — increments failure count, may trip the breaker."""
        async with self._lock:
            self._failure_count += 1

            if self._state == self.HALF_OPEN:
                # Trial failed — re-open immediately
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit_breaker_reopened provider=%s (half-open trial failed)",
                    self.provider,
                )
                return

            if self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit_breaker_tripped provider=%s failures=%d threshold=%d",
                    self.provider,
                    self._failure_count,
                    self.failure_threshold,
                )


# ---------------------------------------------------------------------------
# Process-local breaker registry
# ---------------------------------------------------------------------------

_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()


async def get_breaker(provider: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    """Return (or create) the circuit breaker for *provider*."""
    async with _registry_lock:
        if provider not in _breakers:
            _breakers[provider] = CircuitBreaker(provider, config)
        return _breakers[provider]


def reset_all_breakers() -> None:
    """Clear the breaker registry — useful for tests."""
    _breakers.clear()
