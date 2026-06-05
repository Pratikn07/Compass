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

SIDEBAR_TABLES = [
    "watchlists",
    "watchlist_items",
    "system_health",
]


def _migration_sql() -> str:
    migrations = sorted(Path("supabase/migrations").glob("*r6_4_storage*.sql"))
    assert len(migrations) == 1
    return migrations[0].read_text(encoding="utf-8").lower()


def _sidebar_migration_sql() -> str:
    migrations = sorted(Path("supabase/migrations").glob("*runs_sidebar_filters*.sql"))
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


def test_sidebar_filters_migration_adds_attention_and_health_contracts() -> None:
    sql = _sidebar_migration_sql()

    assert "alter table prescient_storage.decision_records" in sql
    assert "attention_status text not null default 'normal'" in sql
    assert "attention_reasons text[] not null default '{}'::text[]" in sql
    assert "decision_records_attention_status_check" in sql
    assert "normal" in sql
    assert "needs_attention" in sql
    assert "system_health_component_check" in sql
    assert "market_data" in sql
    assert "pricing_engine" in sql
    assert "risk_engine" in sql
    assert "system_health_status_check" in sql
    assert "healthy" in sql
    assert "degraded" in sql
    assert "blocked" in sql
    assert "unknown" in sql


def test_sidebar_filters_migration_creates_read_only_sidebar_tables() -> None:
    sql = _sidebar_migration_sql()

    for table in SIDEBAR_TABLES:
        assert f"create table if not exists prescient_storage.{table}" in sql
        assert f"alter table prescient_storage.{table} enable row level security" in sql
        assert f"create policy authenticated_read on prescient_storage.{table}" in sql
        assert "for select to authenticated" in sql

    assert "grant select on all tables in schema prescient_storage to authenticated" in sql
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "security definer" not in sql
    assert "auth.role()" not in sql
