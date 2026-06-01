from __future__ import annotations

# Placeholder for async DB session utilities.
# This service can store agent_runs/agent_actions locally if desired.

from app.config import settings


def get_database_url() -> str:
    return settings.database_url
