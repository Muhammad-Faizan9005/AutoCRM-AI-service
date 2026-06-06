from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_new_ai_tables_have_rls_and_service_role_policies() -> None:
    migration = (
        ROOT_DIR
        / "alembic"
        / "versions"
        / "0006_harden_ai_context_and_trace_rls.py"
    ).read_text(encoding="utf-8")

    for table in ["ai_run_traces", "ai_context_chunks"]:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in migration
        assert f"CREATE POLICY {table}_service_role_all" in migration
        assert f"FOR ALL TO service_role" in migration
