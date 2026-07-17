from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from compass.storage.repository import SupabaseRepository

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")


class Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class Query:
    def __init__(self, table: str, database: Database) -> None:
        self.table = table
        self.database = database
        self.filters: list[tuple[str, object]] = []
        self.inserted: list[dict] | None = None
        self.upserted: tuple[list[dict], str] | None = None
        self.updated: dict | None = None
        self.ordering: tuple[str, bool] | None = None
        self.maximum: int | None = None
        self.offset = 0

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key: str, value: object):
        self.filters.append((key, value))
        return self

    def order(self, key: str, desc: bool = False):
        self.ordering = (key, desc)
        return self

    def limit(self, maximum: int):
        self.maximum = maximum
        return self

    def range(self, start: int, end: int):
        self.offset = start
        self.maximum = end - start + 1
        return self

    def gte(self, key: str, value: object):
        self.filters.append((f"{key}__gte", value))
        return self

    def insert(self, rows: list[dict]):
        self.inserted = rows
        return self

    def upsert(self, rows: list[dict], on_conflict: str):
        self.upserted = (rows, on_conflict)
        return self

    def update(self, payload: dict):
        self.updated = payload
        return self

    def execute(self) -> Result:
        if self.upserted is not None:
            incoming, on_conflict = self.upserted
            keys = [key.strip() for key in on_conflict.split(",")]
            stored = self.database.tables[self.table]
            output = []
            for row in incoming:
                match = next(
                    (
                        existing
                        for existing in stored
                        if all(str(existing.get(key)) == str(row.get(key)) for key in keys)
                    ),
                    None,
                )
                if match is None:
                    match = dict(row)
                    stored.append(match)
                else:
                    match.update(row)
                output.append(dict(match))
            return Result(output)
        if self.inserted is not None:
            self.database.tables[self.table].extend(dict(row) for row in self.inserted)
            return Result([dict(row) for row in self.inserted])

        rows = [
            row
            for row in self.database.tables[self.table]
            if all(
                str(row.get(key.removesuffix("__gte"))) >= str(value)
                if key.endswith("__gte")
                else str(row.get(key)) == str(value)
                for key, value in self.filters
            )
        ]
        if self.updated is not None:
            for row in rows:
                row.update(self.updated)
        if self.ordering is not None:
            key, desc = self.ordering
            rows.sort(key=lambda row: str(row.get(key) or ""), reverse=desc)
        if self.maximum is not None:
            rows = rows[self.offset : self.offset + self.maximum]
        return Result([dict(row) for row in rows])


class Schema:
    def __init__(self, database: Database) -> None:
        self.database = database

    def table(self, name: str) -> Query:
        self.database.requested_tables.append(name)
        return Query(name, self.database)


class Database:
    def __init__(self) -> None:
        self.requested_schemas: list[str] = []
        self.requested_tables: list[str] = []
        self.tables: dict[str, list[dict]] = {
            "runs": [],
            "themes": [],
            "theme_state_daily": [],
            "overrides": [],
            "decision_records": [],
            "journal_records": [],
            "rule_changes": [],
            "learning_reports": [],
            "provider_snapshots": [],
            "provider_errors": [],
            "system_health": [],
            "price_bars": [],
            "storage_write_audit": [],
        }

    def schema(self, name: str) -> Schema:
        self.requested_schemas.append(name)
        return Schema(self)


def test_repository_uses_compass_schema_and_filters_reads_by_owner() -> None:
    database = Database()
    database.tables["themes"] = [
        {"owner_id": str(OWNER_ID), "slug": "ai-chips", "name": "AI chips"},
        {"owner_id": str(OTHER_ID), "slug": "private", "name": "Other"},
    ]
    database.tables["theme_state_daily"] = [
        {"owner_id": str(OWNER_ID), "d": "2026-07-16", "theme_slug": "ai-chips"}
    ]

    rows = SupabaseRepository(client=database, owner_id=OWNER_ID).list_themes()

    assert database.requested_schemas == ["compass_storage"] * 3
    assert [row["slug"] for row in rows] == ["ai-chips"]


def test_repository_adds_owner_to_every_insert() -> None:
    database = Database()
    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)

    row = repository.create_override(what="sold early", reason="changed my mind")

    assert row["owner_id"] == str(OWNER_ID)
    assert database.tables["overrides"] == [row]


def test_repository_ping_uses_owner_scoped_runs_query() -> None:
    database = Database()
    database.tables["runs"] = [
        {"owner_id": str(OTHER_ID), "run_id": "other"},
        {"owner_id": str(OWNER_ID), "run_id": "mine"},
    ]

    SupabaseRepository(client=database, owner_id=OWNER_ID).ping()

    assert database.requested_tables == ["runs"]


def test_repository_advisor_reads_are_owner_scoped() -> None:
    database = Database()
    database.tables["themes"] = [
        {"owner_id": str(OWNER_ID), "slug": "ai-chips", "name": "AI chips"}
    ]
    database.tables["theme_memberships"] = [
        {"owner_id": str(OWNER_ID), "theme_slug": "ai-chips", "ticker": "NVDA"},
        {"owner_id": str(OTHER_ID), "theme_slug": "ai-chips", "ticker": "OTHER"},
    ]
    database.tables["theme_state_daily"] = [
        {"owner_id": str(OWNER_ID), "theme_slug": "ai-chips", "d": "2026-07-16"}
    ]
    database.tables["decision_records"] = [
        {
            "owner_id": str(OWNER_ID),
            "decision_id": "mine",
            "decision_date": "2026-07-16",
        },
        {
            "owner_id": str(OTHER_ID),
            "decision_id": "other",
            "decision_date": "2026-07-16",
        },
    ]
    database.tables["journal_records"] = [
        {
            "owner_id": str(OWNER_ID),
            "journal_record_id": "journal-mine",
            "trading_date": "2026-07-16",
        }
    ]

    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)
    detail = repository.theme_detail("ai-chips", days=30)
    today = repository.recommendations_today()
    journal = repository.journal(days=30)

    assert detail is not None
    assert [member["ticker"] for member in detail["members"]] == ["NVDA"]
    assert today["recommendations"][0]["decision_id"] == "mine"
    assert journal["records"][0]["journal_record_id"] == "journal-mine"


def test_governance_writes_create_owner_scoped_journal_records() -> None:
    database = Database()
    database.tables["decision_records"] = [
        {
            "owner_id": str(OWNER_ID),
            "decision_id": "decision-1",
            "decision_date": "2026-07-16",
            "acknowledged_at": None,
        }
    ]
    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)

    override = repository.create_override(what="sold early", reason="changed my mind")
    acknowledged = repository.acknowledge_decision(
        "decision-1", acknowledged_at="2026-07-17T00:00:00+00:00"
    )
    rule = repository.create_rule_change(
        {
            "change": {"sma_n": 150},
            "proposed_at": "2026-07-17T00:00:00+00:00",
            "effective_at": "2026-07-19T00:00:00+00:00",
            "approved": False,
        }
    )

    assert override["owner_id"] == str(OWNER_ID)
    assert acknowledged is not None
    assert acknowledged["acknowledged_at"] is not None
    assert rule["owner_id"] == str(OWNER_ID)
    assert {row["record_type"] for row in database.tables["journal_records"]} == {
        "override",
        "acknowledgement",
        "rule_change",
    }
    assert all(row["owner_id"] == str(OWNER_ID) for row in database.tables["journal_records"])


def test_research_and_operations_reads_are_paginated_and_owner_scoped() -> None:
    database = Database()
    database.tables["decision_records"] = [
        {
            "owner_id": str(OWNER_ID),
            "decision_id": f"decision-{index}",
            "decision_date": f"2026-07-{16 - index:02d}",
        }
        for index in range(3)
    ]
    database.tables["decision_records"].append(
        {"owner_id": str(OTHER_ID), "decision_id": "other", "decision_date": "2026-07-17"}
    )
    database.tables["runs"] = [
        {
            "owner_id": str(OWNER_ID),
            "run_id": f"run-{index}",
            "started_at": f"2026-07-{16 - index:02d}T00:00:00+00:00",
        }
        for index in range(3)
    ]
    database.tables["learning_reports"] = [
        {
            "owner_id": str(OWNER_ID),
            "learning_report_id": "report-1",
            "report_date": "2026-07-16",
            "report_type": "edge_backtest",
        }
    ]
    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)

    decisions, decision_cursor = repository.list_decisions(limit=2, cursor=None)
    later_decisions, _ = repository.list_decisions(limit=2, cursor=decision_cursor)
    runs, run_cursor = repository.list_runs(limit=2, cursor=None)

    assert [row["decision_id"] for row in decisions] == ["decision-0", "decision-1"]
    assert [row["decision_id"] for row in later_decisions] == ["decision-2"]
    assert run_cursor is not None
    assert len(runs) == 2
    assert repository.latest_backtest()["learning_report_id"] == "report-1"


def test_health_views_return_latest_owner_records() -> None:
    database = Database()
    now = datetime.now(UTC)
    database.tables["provider_snapshots"] = [
        {
            "owner_id": str(OWNER_ID),
            "provider_snapshot_id": "snapshot-1",
            "provider": "yahoo",
            "created_at": now.isoformat(),
        }
    ]
    database.tables["provider_errors"] = [
        {
            "owner_id": str(OWNER_ID),
            "provider_error_id": "error-1",
            "provider": "sec",
            "created_at": now.isoformat(),
        }
    ]
    database.tables["system_health"] = [
        {
            "owner_id": str(OWNER_ID),
            "system_health_id": "health-1",
            "component": "database",
            "status": "healthy",
            "created_at": now.isoformat(),
        }
    ]
    database.tables["runs"] = [
        {
            "owner_id": str(OWNER_ID),
            "run_id": "run-1",
            "status": "succeeded",
            "started_at": (now - timedelta(hours=1)).isoformat(),
        }
    ]

    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)

    assert repository.provider_health()["providers"][0]["provider"] == "yahoo"
    assert repository.provider_health()["recent_errors"][0]["provider"] == "sec"
    assert repository.system_health()[0]["component"] == "database"
    assert repository.detailed_health()["status"] == "healthy"


def test_nightly_lifecycle_records_are_idempotent_and_owner_scoped() -> None:
    database = Database()
    repository = SupabaseRepository(client=database, owner_id=OWNER_ID)
    run = {
        "run_id": "nightly:2026-07-17",
        "run_type": "nightly",
        "trigger_type": "scheduled",
        "scheduled_date": "2026-07-17",
        "status": "running",
        "payload": {},
    }

    repository.start_run(run)
    repository.start_run(run)
    repository.record_provider_error(
        {
            "provider_error_id": "error:nightly:2026-07-17:yahoo",
            "provider": "yahoo",
            "error_type": "TimeoutError",
            "message": "Provider step failed",
            "payload": {},
        }
    )
    repository.record_storage_audit(
        {
            "storage_write_audit_id": "audit:nightly:2026-07-17:yahoo",
            "provider": "yahoo",
            "table_name": "price_bars",
            "attempted_record_count": 12,
            "written_record_count": 12,
            "error_count": 0,
            "payload": {},
        }
    )
    repository.record_system_health(
        {
            "system_health_id": "health:nightly:2026-07-17:database",
            "component": "database",
            "status": "healthy",
            "payload": {},
        }
    )
    repository.persist_learning_report(
        {
            "learning_report_id": "edge-backtest:2026-07-17",
            "report_date": "2026-07-17",
            "report_type": "edge_backtest",
            "payload": {"scorecards": {}},
        }
    )
    finished = repository.finish_run(
        run["run_id"], status="partial", payload={"failed_steps": 1}
    )

    assert len(database.tables["runs"]) == 1
    assert finished["status"] == "partial"
    for table in (
        "runs",
        "provider_errors",
        "storage_write_audit",
        "system_health",
        "learning_reports",
    ):
        assert database.tables[table][0]["owner_id"] == str(OWNER_ID)
