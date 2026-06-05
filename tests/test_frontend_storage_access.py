from __future__ import annotations

from pathlib import Path


TABLES = [
    "runs",
    "journal_records",
    "decision_records",
    "lifecycle_records",
    "provider_snapshots",
    "provider_errors",
    "learning_reports",
    "storage_write_audit",
    "watchlists",
    "watchlist_items",
    "system_health",
]


def _frontend_access_sql() -> str:
    migrations = sorted(Path("supabase/migrations").glob("*.sql"))
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in migrations)


def test_local_supabase_api_exposes_prescient_storage_schema() -> None:
    config = Path("supabase/config.toml").read_text(encoding="utf-8")

    assert 'schemas = ["public", "graphql_public", "prescient_storage"]' in config


def test_frontend_access_migration_grants_authenticated_read_only_access() -> None:
    sql = _frontend_access_sql()

    assert "grant usage on schema prescient_storage to authenticated" in sql
    assert "grant select on all tables in schema prescient_storage to authenticated" in sql
    assert "to anon" not in sql
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "security definer" not in sql
    assert "auth.role()" not in sql


def test_frontend_access_migration_creates_authenticated_select_policy_per_table() -> None:
    sql = _frontend_access_sql()

    for table in TABLES:
        assert f"create policy authenticated_read on prescient_storage.{table}" in sql
        assert "for select to authenticated" in sql
        assert "using (true)" in sql
