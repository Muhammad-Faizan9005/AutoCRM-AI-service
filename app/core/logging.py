from __future__ import annotations

import logging

from app.core.correlation import get_correlation_id, get_run_id


class CorrelationFilter(logging.Filter):
    """Inject ``correlation_id`` and ``run_id`` from context vars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        record.run_id = get_run_id()  # type: ignore[attr-defined]
        return True


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid adding duplicate handlers on reloads
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level.upper())
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s"
            " [cid=%(correlation_id)s rid=%(run_id)s]"
            " %(message)s"
        )
        handler.setFormatter(formatter)
        handler.addFilter(CorrelationFilter())
        root.addHandler(handler)
    else:
        # Ensure existing handlers also have the filter
        for handler in root.handlers:
            if not any(isinstance(f, CorrelationFilter) for f in handler.filters):
                handler.addFilter(CorrelationFilter())
