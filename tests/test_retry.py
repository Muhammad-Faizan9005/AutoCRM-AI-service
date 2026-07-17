"""Tests for app.core.retry — jittered backoff, retryability classifier, failure categoriser."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.failure import FailureCategory
from app.core.retry import (
    RetryPolicy,
    classify_failure,
    is_retryable,
    retry_async,
)


# ---------------------------------------------------------------------------
# Helpers — build httpx exceptions with proper constructor args
# ---------------------------------------------------------------------------

def _make_http_error(status_code: int, message: str = "error") -> httpx.HTTPStatusError:
    """Create an HTTPStatusError with the required request/response objects."""
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(message, request=request, response=response)


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------


class TestIsRetryable:
    def test_timeout_is_retryable(self):
        assert is_retryable(httpx.TimeoutException("timeout"))

    def test_connect_error_is_retryable(self):
        assert is_retryable(httpx.ConnectError("refused"))

    def test_429_is_retryable(self):
        assert is_retryable(_make_http_error(429))

    def test_500_is_retryable(self):
        assert is_retryable(_make_http_error(500))

    def test_502_is_retryable(self):
        assert is_retryable(_make_http_error(502))

    def test_503_is_retryable(self):
        assert is_retryable(_make_http_error(503))

    def test_504_is_retryable(self):
        assert is_retryable(_make_http_error(504))

    def test_401_not_retryable(self):
        assert not is_retryable(_make_http_error(401))

    def test_403_not_retryable(self):
        assert not is_retryable(_make_http_error(403))

    def test_404_not_retryable(self):
        assert not is_retryable(_make_http_error(404))

    def test_400_not_retryable(self):
        assert not is_retryable(_make_http_error(400))

    def test_422_not_retryable(self):
        assert not is_retryable(_make_http_error(422))

    def test_runtime_error_not_retryable(self):
        assert not is_retryable(RuntimeError("Unsupported LLM provider"))

    def test_value_error_not_retryable(self):
        assert not is_retryable(ValueError("bad value"))


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_timeout(self):
        assert classify_failure(httpx.TimeoutException("timeout")) == FailureCategory.LLM_TIMEOUT.value

    def test_connect_error(self):
        assert classify_failure(httpx.ConnectError("connection refused")) == FailureCategory.LLM_CONNECTION_ERROR.value

    def test_429_rate_limited(self):
        assert classify_failure(_make_http_error(429)) == FailureCategory.RATE_LIMITED.value

    def test_401_auth(self):
        assert classify_failure(_make_http_error(401)) == FailureCategory.AUTHENTICATION_ERROR.value

    def test_403_auth(self):
        assert classify_failure(_make_http_error(403)) == FailureCategory.AUTHENTICATION_ERROR.value

    def test_500_server(self):
        assert classify_failure(_make_http_error(500)) == FailureCategory.LLM_SERVER_ERROR.value

    def test_502_server(self):
        assert classify_failure(_make_http_error(502)) == FailureCategory.LLM_SERVER_ERROR.value

    def test_400_invalid_request(self):
        assert classify_failure(_make_http_error(400)) == FailureCategory.INVALID_REQUEST.value

    def test_404_invalid_model(self):
        assert classify_failure(_make_http_error(404)) == FailureCategory.INVALID_MODEL.value

    def test_runtime_unsupported(self):
        assert classify_failure(RuntimeError("Unsupported provider")) == FailureCategory.INVALID_MODEL.value

    def test_runtime_api_key(self):
        assert classify_failure(RuntimeError("OPENAI_API_KEY is not configured")) == FailureCategory.AUTHENTICATION_ERROR.value

    def test_unknown(self):
        assert classify_failure(ValueError("some error")) == FailureCategory.UNKNOWN_ERROR.value


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------


class TestRetryAsync:
    async def test_succeeds_on_first_try(self):
        calls = []

        async def fn():
            calls.append(1)
            return "ok"

        result = await retry_async(fn, attempts=3, base_delay=0.001, max_delay=0.01)
        assert result == "ok"
        assert len(calls) == 1

    async def test_retries_on_retryable_then_succeeds(self):
        attempts = []

        async def fn():
            attempts.append(1)
            if len(attempts) < 3:
                raise httpx.TimeoutException("timeout")
            return "recovered"

        result = await retry_async(fn, attempts=5, base_delay=0.001, max_delay=0.01)
        assert result == "recovered"
        assert len(attempts) == 3

    async def test_raises_on_non_retryable(self):
        async def fn():
            raise RuntimeError("unsupported")

        with pytest.raises(RuntimeError, match="unsupported"):
            await retry_async(fn, attempts=3, base_delay=0.001, max_delay=0.01)

    async def test_raises_after_exhausted_attempts(self):
        async def fn():
            raise httpx.TimeoutException("timeout")

        with pytest.raises(httpx.TimeoutException):
            await retry_async(fn, attempts=2, base_delay=0.001, max_delay=0.01)

    async def test_on_retry_callback_fires(self):
        retries = []

        async def fn():
            if len(retries) < 2:
                raise httpx.TimeoutException("timeout")
            return "ok"

        def on_retry(attempt, exc, delay):
            retries.append((attempt, type(exc).__name__, delay))

        await retry_async(fn, attempts=5, base_delay=0.001, max_delay=0.01, on_retry=on_retry)
        assert len(retries) == 2
        assert retries[0][0] == 1
        assert retries[1][0] == 2

    async def test_jitter_produces_bounded_delays(self):
        delays = []

        async def fn():
            if len(delays) < 5:
                raise httpx.TimeoutException("timeout")
            return "ok"

        def on_retry(attempt, exc, delay):
            delays.append(delay)

        await retry_async(fn, attempts=10, base_delay=1.0, max_delay=10.0, on_retry=on_retry)
        # All delays should be non-negative and bounded by max_delay
        for d in delays:
            assert 0 <= d <= 10.0

    async def test_policy_overrides_parameters(self):
        calls = []

        async def fn():
            calls.append(1)
            if len(calls) < 2:
                raise httpx.TimeoutException("timeout")
            return "ok"

        policy = RetryPolicy(attempts=5, base_delay=0.001, max_delay=0.01)
        result = await retry_async(fn, attempts=1, policy=policy)  # attempts=1 should be overridden
        assert result == "ok"
        assert len(calls) == 2

    async def test_non_retryable_raises_immediately_no_retry(self):
        """Non-retryable errors should raise on first attempt without retry."""
        calls = []

        async def fn():
            calls.append(1)
            raise _make_http_error(401)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_async(fn, attempts=5, base_delay=0.001, max_delay=0.01)
        assert len(calls) == 1  # no retries attempted
