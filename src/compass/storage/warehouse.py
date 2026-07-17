from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID, uuid4

from compass.config import require_env
from compass.models import FundamentalsQuarter, PriceBar
from compass.storage.repository import SupabaseRepository
from compass.universe import BENCHMARKS, ETFS, MEMBERS, THEMES

_CHUNK_SIZE = 500


def make_client():
    from supabase import create_client

    return create_client(
        require_env("SUPABASE_URL"),
        require_env("SUPABASE_SERVICE_ROLE_KEY"),
    )


def make_warehouse() -> Warehouse:
    return Warehouse(
        client=make_client(),
        owner_id=UUID(require_env("COMPASS_OWNER_USER_ID")),
    )


class Warehouse(SupabaseRepository):
    def __init__(self, client, owner_id: UUID | None = None) -> None:
        resolved_owner = owner_id or UUID(require_env("COMPASS_OWNER_USER_ID"))
        super().__init__(client=client, owner_id=resolved_owner)

    def select(self, table: str, columns: str = "*"):
        return self._select(table, columns)

    def fetch_all(
        self,
        table: str,
        columns: str,
        *,
        order_by: str | None = None,
        page_size: int = 1_000,
    ) -> list[dict]:
        output: list[dict] = []
        start = 0
        while True:
            query = self._select(table, columns)
            if order_by is not None:
                query = query.order(order_by)
            page = query.range(start, start + page_size - 1).execute().data
            output.extend(page)
            if len(page) < page_size:
                return output
            start += page_size

    def upsert_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> int:
        owned = [{**row, "owner_id": self._owner} for row in rows]
        for index in range(0, len(owned), _CHUNK_SIZE):
            self._table(table).upsert(
                owned[index : index + _CHUNK_SIZE],
                on_conflict=on_conflict,
            ).execute()
        return len(owned)

    def seed_universe(self) -> dict[str, int]:
        companies = (
            [{"ticker": row.ticker, "name": row.name, "kind": "stock"} for row in MEMBERS]
            + [{"ticker": row.ticker, "name": row.name, "kind": "etf"} for row in ETFS]
            + [
                {"ticker": row.ticker, "name": row.name, "kind": "benchmark"}
                for row in BENCHMARKS
            ]
        )
        themes = [
            {
                "slug": theme.slug,
                "name": theme.name,
                "etf_ticker": theme.etf_ticker,
                "etf_is_primary": theme.etf_is_primary,
            }
            for theme in THEMES
        ]
        memberships = [
            {
                "theme_slug": member.theme_slug,
                "ticker": member.ticker,
                "member_since": member.member_since.isoformat(),
                "member_until": (
                    member.member_until.isoformat() if member.member_until else None
                ),
                "justification": member.justification,
            }
            for member in MEMBERS
        ]
        return {
            "companies": self.upsert_rows("companies", companies, on_conflict="ticker"),
            "themes": self.upsert_rows("themes", themes, on_conflict="slug"),
            "memberships": self.upsert_rows(
                "theme_memberships",
                memberships,
                on_conflict="owner_id,theme_slug,ticker,member_since",
            ),
        }

    def upsert_price_bars(self, bars: list[PriceBar]) -> int:
        return self.upsert_rows(
            "price_bars",
            [bar.to_row() for bar in bars],
            on_conflict="owner_id,ticker,d",
        )

    def upsert_fundamentals(self, rows: list[FundamentalsQuarter]) -> int:
        return self.upsert_rows(
            "fundamentals",
            [row.to_row() for row in rows],
            on_conflict="owner_id,ticker,fiscal_quarter_end",
        )

    def upsert_decisions(self, *, run_id: str, rows: list[dict[str, Any]]) -> int:
        decisions = []
        for row in rows:
            key = ":".join(
                (self._owner, row["d"], row["hypothesis"], row["instrument"])
            )
            decision_id = f"decision:{hashlib.sha256(key.encode()).hexdigest()[:32]}"
            decisions.append(
                {
                    "decision_id": decision_id,
                    "run_id": run_id,
                    "decision_date": row["d"],
                    "hypothesis": row["hypothesis"],
                    "instrument": row["instrument"],
                    "theme_slug": row["instrument"] if row["instrument"] != "-" else None,
                    "action": row["action"],
                    "reasoning": row.get("reasoning", {}),
                    "base_rate": row.get("base_rate"),
                }
            )
        count = self.upsert_rows(
            "decision_records",
            decisions,
            on_conflict="owner_id,decision_date,hypothesis,instrument",
        )
        journals = [
            {
                "journal_record_id": f"recommendation:{row['decision_id']}",
                "record_type": "recommendation",
                "run_id": run_id,
                "decision_id": row["decision_id"],
                "trading_date": row["decision_date"],
                "target": row["instrument"],
                "theme": row["theme_slug"],
                "source": "compass_nightly",
                "payload": {
                    "action": row["action"],
                    "reasoning": row["reasoning"],
                    "base_rate": row["base_rate"],
                },
            }
            for row in decisions
        ]
        self.upsert_rows(
            "journal_records",
            journals,
            on_conflict="journal_record_id",
        )
        return count

    def log_run(
        self,
        *,
        source: str,
        ticker: str,
        records: int,
        status: str,
        error: str | None = None,
    ) -> None:
        audit_id = f"ingest-audit:{uuid4()}"
        self.record_storage_audit(
            {
                "storage_write_audit_id": audit_id,
                "provider": source,
                "table_name": "ingest",
                "attempted_record_count": records,
                "written_record_count": records if status == "ok" else 0,
                "error_count": 0 if status == "ok" else 1,
                "payload": {"ticker": ticker},
            }
        )
        if error is not None:
            self.record_provider_error(
                {
                    "provider_error_id": f"ingest-error:{uuid4()}",
                    "provider": source,
                    "error_type": "IngestError",
                    "target": ticker,
                    "source": "backfill",
                    "message": "Provider ingest failed; inspect local logs.",
                    "payload": {},
                }
            )
