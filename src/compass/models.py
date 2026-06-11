"""Normalized record types returned by adapters and written by the store.

`ingested_at` is set by the database default at write time (point-in-time
provenance), so models intentionally do NOT carry it (vanta pattern).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PriceBar:
    ticker: str
    d: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float
    volume: int | None
    source: str

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "d": self.d.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adj_close": self.adj_close,
            "volume": self.volume,
            "source": self.source,
        }


@dataclass(frozen=True)
class FundamentalsQuarter:
    ticker: str
    fiscal_quarter_end: date
    # No-lookahead anchor: a row without report_date is unusable in Phase 2.
    report_date: date | None
    revenue: float | None
    operating_income: float | None
    eps_estimate: float | None
    eps_actual: float | None
    surprise_pct: float | None
    source: str

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "fiscal_quarter_end": self.fiscal_quarter_end.isoformat(),
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "revenue": self.revenue,
            "operating_income": self.operating_income,
            "eps_estimate": self.eps_estimate,
            "eps_actual": self.eps_actual,
            "surprise_pct": self.surprise_pct,
            "source": self.source,
        }
