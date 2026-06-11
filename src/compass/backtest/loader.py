"""Load prices and fundamentals from Supabase into memory, with a local
snapshot so the slow pull happens once.

The snapshot lives in .cache/backtest/market.json (gitignored, rebuildable).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import CACHE_DIR
from .calendar import TradingCalendar
from .series import Series

SNAPSHOT = CACHE_DIR / "backtest" / "market.json"
_PAGE = 1000


@dataclass(frozen=True)
class FundRow:
    fiscal_quarter_end: date
    report_date: date | None
    revenue: float | None
    operating_income: float | None
    surprise_pct: float | None


class Market:
    """In-memory market data: adjusted-close series, volumes, fundamentals."""

    def __init__(
        self,
        prices: dict[str, Series],
        volumes: dict[str, Series],
        fundamentals: dict[str, list[FundRow]],
    ) -> None:
        self.prices = prices
        self.volumes = volumes
        self.fundamentals = fundamentals

    def calendar(self) -> TradingCalendar:
        spy = self.prices.get("SPY")
        if spy is None or not spy.dates:
            raise RuntimeError("SPY prices missing — backfill prices first")
        return TradingCalendar(spy.dates)

    def reported_fundamentals(self, ticker: str, on: date) -> list[FundRow]:
        """Rows knowable on `on`: report_date present and report_date < on
        (report_date + 1 trading day rule, conservatively daily). Sorted by
        fiscal quarter end."""
        rows = [
            r for r in self.fundamentals.get(ticker, [])
            if r.report_date is not None and r.report_date < on
        ]
        return sorted(rows, key=lambda r: r.fiscal_quarter_end)


def _fetch_all(client, table: str, columns: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            client.table(table)
            .select(columns)
            .order("ticker")
            .order("d" if table == "compass_price_bars" else "fiscal_quarter_end")
            .range(start, start + _PAGE - 1)
            .execute()
        ).data
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        start += _PAGE


def _build_snapshot() -> dict:
    from ..store import make_client

    client = make_client()
    print("pulling compass_price_bars from Supabase (one-time; snapshot cached) ...")
    bars = _fetch_all(client, "compass_price_bars", "ticker,d,adj_close,volume")
    print(f"  {len(bars)} bars")
    print("pulling compass_fundamentals ...")
    funds = _fetch_all(
        client,
        "compass_fundamentals",
        "ticker,fiscal_quarter_end,report_date,revenue,operating_income,surprise_pct",
    )
    print(f"  {len(funds)} fundamental quarters")

    prices: dict[str, list] = {}
    for b in bars:
        prices.setdefault(b["ticker"], []).append([b["d"], b["adj_close"], b["volume"]])
    fundamentals: dict[str, list] = {}
    for f in funds:
        fundamentals.setdefault(f["ticker"], []).append(
            [
                f["fiscal_quarter_end"],
                f["report_date"],
                f["revenue"],
                f["operating_income"],
                f["surprise_pct"],
            ]
        )
    return {"prices": prices, "fundamentals": fundamentals}


def load_market(snapshot_path: Path = SNAPSHOT, refresh: bool = False) -> Market:
    if refresh or not snapshot_path.exists():
        snapshot = _build_snapshot()
        try:
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot))
        except OSError as exc:
            print(f"[warn] snapshot not cached ({exc}); continuing in memory")
    else:
        snapshot = json.loads(snapshot_path.read_text())

    prices: dict[str, Series] = {}
    volumes: dict[str, Series] = {}
    for ticker, rows in snapshot["prices"].items():
        rows.sort(key=lambda r: r[0])
        dates = [date.fromisoformat(r[0]) for r in rows]
        prices[ticker] = Series(dates, [float(r[1]) for r in rows])
        vol_pairs = [
            (d, float(r[2])) for d, r in zip(dates, rows, strict=True) if r[2] is not None
        ]
        volumes[ticker] = Series([p[0] for p in vol_pairs], [p[1] for p in vol_pairs])

    fundamentals: dict[str, list[FundRow]] = {}
    for ticker, rows in snapshot["fundamentals"].items():
        fundamentals[ticker] = [
            FundRow(
                fiscal_quarter_end=date.fromisoformat(r[0]),
                report_date=date.fromisoformat(r[1]) if r[1] else None,
                revenue=r[2],
                operating_income=r[3],
                surprise_pct=r[4],
            )
            for r in rows
        ]
    return Market(prices, volumes, fundamentals)
