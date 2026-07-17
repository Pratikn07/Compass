from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "companies",
    "themes",
    "theme_memberships",
    "price_bars",
    "fundamentals",
    "theme_state_daily",
    "decision_records",
    "overrides",
    "rule_changes",
    "runs",
    "journal_records",
    "provider_snapshots",
    "provider_errors",
    "learning_reports",
    "storage_write_audit",
    "system_health",
    "watchlists",
    "watchlist_items",
}


def migration_sql() -> str:
    matches = list(
        (ROOT / "supabase" / "migrations").glob("*_unified_compass_storage.sql")
    )
    assert len(matches) == 1
    return matches[0].read_text()


def test_unified_migration_creates_only_owner_scoped_compass_tables() -> None:
    sql = migration_sql().lower()

    assert "create schema if not exists compass_storage" in sql
    for table in TABLES:
        definition = f"create table compass_storage.{table}"
        assert definition in sql
        table_body = sql.split(definition, 1)[1].split(");", 1)[0]
        assert "owner_id uuid not null references auth.users(id)" in table_body

    assert "operator_mode_authorizations" not in sql
    assert "create table compass_storage.orders" not in sql
    assert "create table compass_storage.positions" not in sql


def test_unified_migration_enables_rls_and_owner_policies_on_every_table() -> None:
    sql = migration_sql().lower()

    for table in TABLES:
        assert f"alter table compass_storage.{table} enable row level security" in sql
        assert f"on compass_storage.{table}\n    for select\n    to authenticated" in sql

    assert "using ((select auth.uid()) = owner_id)" in sql
    assert "using (true)" not in sql
    assert "auth.role()" not in sql


def test_unified_migration_keeps_data_api_service_only() -> None:
    sql = migration_sql().lower()

    assert "revoke all on schema compass_storage from anon, authenticated" in sql
    assert (
        "revoke all on all tables in schema compass_storage from anon, authenticated"
        in sql
    )
    assert "grant usage on schema compass_storage to service_role" in sql
    assert "grant all on all tables in schema compass_storage to service_role" in sql
    assert "grant usage, select on all sequences in schema compass_storage to service_role" in sql
    assert "grant select on all tables in schema compass_storage to authenticated" not in sql
    assert "security definer" not in sql


def test_decisions_are_the_single_idempotent_recommendation_source() -> None:
    sql = migration_sql().lower()

    assert "unique (owner_id, decision_date, hypothesis, instrument)" in sql
    assert "create table compass_storage.recommendations" not in sql
