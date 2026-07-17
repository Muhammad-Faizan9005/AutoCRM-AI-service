"""Jittered exponential backoff, retryability classifier, and failure categoriser."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import httpx

from app.core.failure import FailureCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry policy dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetryPolicy:
    """Provider-scoped retry configuration."""

    attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )


# ---------------------------------------------------------------------------
# Retryability classifier
# ---------------------------------------------------------------------------

def is_retryable(exc: BaseException, *, policy: RetryPolicy | None = None) -> bool:
    """Single source of truth: should this exception trigger a retry?

    - **Retry:** ``httpx.TimeoutException``, ``httpx.ConnectError`` /
      ``ConnectTimeout``, ``httpx.HTTPStatusError`` with status 429 or 5xx.
    - **Do NOT retry (permanent):** 401/403 (auth), 404/400/422 (invalid
      model / malformed request), token/context-limit errors, and our own
      ``RuntimeError`` (missing key / unsupported provider).
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        allowed = policy.retryable_status_codes if policy else {429, 500, 502, 503, 504}
        return status_code in allowed
    # RuntimeError covers "unsupported provider", "missing API key", etc.
    # These are permanent configuration problems — never retry.
    return False


# ---------------------------------------------------------------------------
# Failure classifier
# ---------------------------------------------------------------------------

def classify_failure(exc: BaseException) -> str:
    """Map an exception to a structured :class:`FailureCategory` string.

    The returned value is used as:
    - the ``failure_cause`` persisted on failed runs
    - a metrics label for counters / histograms
    """
    # Import here to avoid circular ref at module level
    from app.core.circuit_breaker import CircuitOpenError

    if isinstance(exc, CircuitOpenError):
        return FailureCategory.LLM_CIRCUIT_OPEN.value

    if isinstance(exc, httpx.TimeoutException):
        return FailureCategory.LLM_TIMEOUT.value

    if isinstance(exc, httpx.ConnectError):
        return FailureCategory.LLM_CONNECTION_ERROR.value

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return FailureCategory.RATE_LIMITED.value
        if code in {401, 403}:
            return FailureCategory.AUTHENTICATION_ERROR.value
        if code in {400, 422}:
            return FailureCategory.INVALID_REQUEST.value
        if code == 404:
            return FailureCategory.INVALID_MODEL.value
        if 500 <= code < 600:
            return FailureCategory.LLM_SERVER_ERROR.value

    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        if "api_key" in msg or "token" in msg or "not configured" in msg:
            return FailureCategory.AUTHENTICATION_ERROR.value
        if "unsupported" in msg:
            return FailureCategory.INVALID_MODEL.value
        if "context" in msg and "limit" in msg:
            return FailureCategory.TOKEN_LIMIT_EXCEEDED.value

    return FailureCategory.UNKNOWN_ERROR.value


# ---------------------------------------------------------------------------
# retry_async — jittered exponential backoff
# ---------------------------------------------------------------------------

async def retry_async(
    fn: Callable[..., Awaitable[Any]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    is_retryable: Callable[[BaseException], bool] = is_retryable,
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    policy: RetryPolicy | None = None,
) -> Any:
    """Execute *fn* with jittered exponential backoff.

    Uses the AWS "full jitter" algorithm::

        computed = min(max_delay, base_delay * 2 ** (attempt - 1))
        actual   = random.uniform(0, computed)

    Parameters
    ----------
    fn:
        An async callable (no arguments) to execute.
    attempts:
        Maximum number of attempts (overridden by *policy* if given).
    base_delay / max_delay:
        Backoff parameters (overridden by *policy* if given).
    is_retryable:
        Predicate that decides whether an exception should be retried.
    on_retry:
        ``on_retry(attempt, exc, delay)`` callback fired **before** each
        retry sleep — used to emit metrics and correlation-tagged logs.
    policy:
        If provided, its fields override *attempts*, *base_delay*, *max_delay*.
    """
    if policy is not None:
        attempts = policy.attempts
        base_delay = policy.base_delay
        max_delay = policy.max_delay

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not is_retryable(exc):
                raise
            computed = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = random.uniform(0, computed)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            logger.warning(
                "retry_async attempt=%d/%d delay=%.2fs error=%s",
                attempt,
                attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Should never reach here, but satisfy type checker
    if last_exc is not None:
        raise last_exc
