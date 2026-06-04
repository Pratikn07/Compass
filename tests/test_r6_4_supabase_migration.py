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
]


def _migration_sql() -> str:
    migrations = sorted(Path("supabase/migrations").glob("*r6_4_storage*.sql"))
    assert len(migrations) == 1
    return migrations[0].read_text(encoding="utf-8").lower()


def test_r6_4_migration_creates_private_storage_schema_and_tables() -> None:
    sql = _migration_sql()

    assert "create schema if not exists prescient_storage" in sql
    for table in TABLES:
        assert f"create table if not exists prescient_storage.{table}" in sql
        assert "schema_version integer not null default 1" in sql


def test_r6_4_migration_quotes_current_date_runs_column() -> None:
    sql = _migration_sql()

    assert '"current_date" date' in sql
    assert "\n    current_date date" not in sql


def test_r6_4_migration_enables_rls_and_revokes_public_access() -> None:
    sql = _migration_sql()

    assert "revoke all on schema prescient_storage from anon, authenticated" in sql
    assert "revoke all on all tables in schema prescient_storage from anon, authenticated" in sql
    for table in TABLES:
        assert f"alter table prescient_storage.{table} enable row level security" in sql


def test_r6_4_migration_has_required_query_indexes_without_privileged_code() -> None:
    sql = _migration_sql()

    required_index_fragments = [
        "journal_records_run_id_idx",
        "journal_records_decision_id_idx",
        "journal_records_trading_date_record_type_idx",
        "journal_records_target_theme_idx",
        "journal_records_unresolved_outcomes_idx",
        "provider_snapshots_provider_target_idx",
        "provider_errors_provider_error_type_idx",
        "learning_reports_run_id_idx",
    ]

    for fragment in required_index_fragments:
        assert fragment in sql

    assert "security definer" not in sql
    assert "auth.role()" not in sql
    assert "create policy" not in sql
