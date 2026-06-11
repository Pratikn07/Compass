"""Supabase store layer — the only module that writes to the warehouse.

Tables enforce uniqueness, so writes are upserts (idempotent re-runs).
`ingested_at` is set by the database default, preserving point-in-time
provenance (vanta pattern).
"""
from __future__ import annotations

from typing import Any

from .config import require_env
from .models import FundamentalsQuarter, PriceBar
from .universe import BENCHMARKS, ETFS, MEMBERS, THEMES

_CHUNK = 500


def make_client():
    from supabase import create_client

    return create_client(require_env("SUPABASE_URL"), require_env("SUPABASE_SERVICE_ROLE_KEY"))


class Store:
    def __init__(self, client) -> None:
        self.client = client

    def _upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
        for i in range(0, len(rows), _CHUNK):
            self.client.table(table).upsert(
                rows[i : i + _CHUNK], on_conflict=on_conflict
            ).execute()
        return len(rows)

    def seed_universe(self) -> dict[str, int]:
        companies = (
            [{"ticker": m.ticker, "name": m.name, "kind": "stock"} for m in MEMBERS]
            + [{"ticker": e.ticker, "name": e.name, "kind": "etf"} for e in ETFS]
            + [{"ticker": b.ticker, "name": b.name, "kind": "benchmark"} for b in BENCHMARKS]
        )
        themes = [
            {
                "slug": t.slug,
                "name": t.name,
                "etf_ticker": t.etf_ticker,
                "etf_is_primary": t.etf_is_primary,
            }
            for t in THEMES
        ]
        memberships = [
            {
                "theme_slug": m.theme_slug,
                "ticker": m.ticker,
                "member_since": m.member_since.isoformat(),
                "member_until": m.member_until.isoformat() if m.member_until else None,
                "justification": m.justification,
            }
            for m in MEMBERS
        ]
        return {
            "companies": self._upsert("compass_companies", companies, "ticker"),
            "themes": self._upsert("compass_themes", themes, "slug"),
            "memberships": self._upsert(
                "compass_theme_memberships", memberships, "theme_slug,ticker,member_since"
            ),
        }

    def upsert_price_bars(self, bars: list[PriceBar]) -> int:
        return self._upsert("compass_price_bars", [b.to_row() for b in bars], "ticker,d")

    def upsert_fundamentals(self, rows: list[FundamentalsQuarter]) -> int:
        return self._upsert(
            "compass_fundamentals", [r.to_row() for r in rows], "ticker,fiscal_quarter_end"
        )

    def log_run(
        self, *, source: str, ticker: str, records: int, status: str, error: str | None = None
    ) -> None:
        self.client.table("compass_ingest_runs").insert(
            [{"source": source, "ticker": ticker, "records": records,
              "status": status, "error": error}]
        ).execute()
