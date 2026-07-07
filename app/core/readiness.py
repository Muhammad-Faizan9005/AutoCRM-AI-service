from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ReadinessState:
    ready: bool = False
    backend_connected: bool = False
    database_connected: bool = False
    scheduler_started: bool = False
    reason: str = "starting"
    checked_at: str | None = None
    details: dict[str, object] = field(default_factory=dict)


state = ReadinessState()


def mark_database_connected() -> None:
    state.database_connected = True
    state.checked_at = datetime.now(timezone.utc).isoformat()


def mark_backend_connected(details: dict[str, object] | None = None) -> None:
    state.backend_connected = True
    state.reason = "backend_connected"
    state.checked_at = datetime.now(timezone.utc).isoformat()
    state.details = details or {}


def mark_scheduler_started() -> None:
    state.scheduler_started = True
    state.ready = state.backend_connected and state.database_connected
    state.reason = "ready" if state.ready else state.reason
    state.checked_at = datetime.now(timezone.utc).isoformat()


def mark_ready(reason: str = "ready") -> None:
    state.ready = state.backend_connected and state.database_connected
    state.reason = reason if state.ready else state.reason
    state.checked_at = datetime.now(timezone.utc).isoformat()


def mark_not_ready(reason: str, details: dict[str, object] | None = None) -> None:
    state.ready = False
    state.reason = reason
    state.checked_at = datetime.now(timezone.utc).isoformat()
    state.details = details or {}


def snapshot() -> dict[str, object]:
    return {
        "ready": state.ready,
        "backend_connected": state.backend_connected,
        "database_connected": state.database_connected,
        "scheduler_started": state.scheduler_started,
        "reason": state.reason,
        "checked_at": state.checked_at,
        "details": state.details,
    }
