"""Structured failure categories shared across retry, circuit breaker, and run failure paths."""

from __future__ import annotations

from enum import Enum


class FailureCategory(str, Enum):
    """Structured failure categories for LLM/planner/agent errors.

    Used as:
    - ``failure_cause`` persisted on failed AI runs
    - Metric labels for retry/failure counters
    - Correlation-tagged log context
    """

    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_CONNECTION_ERROR = "LLM_CONNECTION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    LLM_SERVER_ERROR = "LLM_SERVER_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    INVALID_MODEL = "INVALID_MODEL"
    INVALID_REQUEST = "INVALID_REQUEST"
    TOKEN_LIMIT_EXCEEDED = "TOKEN_LIMIT_EXCEEDED"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    LLM_CIRCUIT_OPEN = "LLM_CIRCUIT_OPEN"
    AGENT_LOOP_ERROR = "AGENT_LOOP_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
