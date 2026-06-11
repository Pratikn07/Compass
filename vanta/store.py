"""Supabase store layer — the only module that writes to the warehouse.

Tables enforce uniqueness, so we upsert (idempotent re-runs). `ingested_at`
is set by the database default, preserving point-in-time provenance.
"""
from __future__ import annotations

from typing import Any

from . import config
from .models import EarningsDate, Estimate, Filing, NewsItem, PriceBar


def make_client():
    """Build a Supabase client from env (service role key for writes)."""
    from supabase import create_client

    url = config.require_env("SUPABASE_URL")
    key = config.require_env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


class Store:
    def __init__(self, client):
        self.client = client

    def _upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
        if not rows:
            return 0
        self.client.table(table).upsert(rows, on_conflict=on_conflict).execute()
        return len(rows)

    def seed_tickers(self) -> int:
        rows = [
            {
                "symbol": t.symbol, "name": t.name,
                "theme": t.theme, "role": t.role,
            }
            for t in config.UNIVERSE
        ]
        return self._upsert("tickers", rows, "symbol")

    def upsert_news(self, items: list[NewsItem]) -> int:
        return self._upsert("news", [i.to_row() for i in items], "ticker,source,url")

    def upsert_filings(self, items: list[Filing]) -> int:
        return self._upsert("filings", [i.to_row() for i in items], "ticker,url")

    def upsert_earnings_dates(self, items: list[EarningsDate]) -> int:
        return self._upsert(
            "earnings_dates", [i.to_row() for i in items], "ticker,report_date"
        )

    def upsert_estimates(self, items: list[Estimate]) -> int:
        return self._upsert(
            "estimates", [i.to_row() for i in items], "ticker,period,as_of"
        )

    def upsert_prices(self, items: list[PriceBar]) -> int:
        return self._upsert("prices", [i.to_row() for i in items], "ticker,date")

    def log_run(self, *, source: str, ticker: str, records: int,
                status: str, error: str | None = None) -> None:
        self.client.table("ingest_runs").insert([{
            "source": source, "ticker": ticker,
            "records": records, "status": status, "error": error,
        }]).execute()
