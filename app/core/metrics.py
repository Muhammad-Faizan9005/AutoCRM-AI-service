"""Lightweight in-process operational metrics (no Prometheus dependency).

Provides simple Counter and Histogram classes with label support and a
``get_metrics_snapshot()`` function that returns a JSON-serialisable dict
suitable for the ``/metrics`` endpoint.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class Counter:
    """A simple monotonically-increasing counter with label support."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"labels": dict(key), "value": value}
                for key, value in self._values.items()
            ]


class Histogram:
    """A simple histogram that tracks count, sum, and basic bucket distribution."""

    _DEFAULT_BUCKETS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf"))

    def __init__(self, name: str, description: str = "", buckets: tuple[float, ...] | None = None) -> None:
        self.name = name
        self.description = description
        self._buckets = buckets or self._DEFAULT_BUCKETS
        self._data: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _ensure_key(self, key: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        if key not in self._data:
            self._data[key] = {
                "count": 0,
                "sum": 0.0,
                "buckets": {str(b): 0 for b in self._buckets},
            }
        return self._data[key]

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            entry = self._ensure_key(key)
            entry["count"] += 1
            entry["sum"] += value
            for b in self._buckets:
                if value <= b:
                    entry["buckets"][str(b)] += 1

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"labels": dict(key), **data}
                for key, data in self._data.items()
            ]


class Gauge:
    """A simple gauge that can go up and down."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[key] += amount

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"labels": dict(key), "value": value}
                for key, value in self._values.items()
            ]


# ---------------------------------------------------------------------------
# Pre-defined metrics (singleton instances)
# ---------------------------------------------------------------------------

planner_retries_total = Counter(
    "planner_retries_total",
    "Total planner/LLM retries by provider and failure category",
)

planner_failures_total = Counter(
    "planner_failures_total",
    "Total planner failures by failure category",
)

content_generation_failures_total = Counter(
    "content_generation_failures_total",
    "Total content generation failures by failure category",
)

llm_request_latency_ms = Histogram(
    "llm_request_latency_ms",
    "LLM request latency in milliseconds by provider and workflow",
)

approval_requests_total = Counter(
    "approval_requests_total",
    "Total approval requests by action type",
)

circuit_breaker_trips_total = Counter(
    "circuit_breaker_trips_total",
    "Total circuit breaker trips by provider",
)

circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Current circuit breaker state by provider (0=closed, 1=open, 2=half_open)",
)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_ALL_METRICS: list[Counter | Histogram | Gauge] = [
    planner_retries_total,
    planner_failures_total,
    content_generation_failures_total,
    llm_request_latency_ms,
    approval_requests_total,
    circuit_breaker_trips_total,
    circuit_breaker_state,
]


def get_metrics_snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of all registered metrics."""
    result: dict[str, Any] = {}
    for metric in _ALL_METRICS:
        result[metric.name] = {
            "description": metric.description,
            "type": type(metric).__name__.lower(),
            "data": metric.snapshot(),
        }
    return result
