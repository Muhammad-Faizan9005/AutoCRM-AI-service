"""Correlation ID and run ID propagation via ``contextvars``.

A ``correlation_id`` (uuid4 string) is created at event ingress and threaded
through the entire pipeline via context variables.  The logging filter in
``app.core.logging`` injects these values into every log record so all logs
for a single request share a common identifier.
"""

from __future__ import annotations

import contextvars
import uuid

_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
_run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "run_id", default=""
)


def new_correlation_id() -> str:
    """Generate and return a new uuid4 correlation ID (does NOT set the var)."""
    return str(uuid.uuid4())


def set_correlation_id(cid: str) -> None:
    _correlation_id_var.set(cid)


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def set_run_id(rid: str) -> None:
    _run_id_var.set(rid)


def get_run_id() -> str:
    return _run_id_var.get()
