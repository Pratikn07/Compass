"""Normalized record types returned by adapters and written by the store.

Every fact-bearing row is enriched with `ingested_at` at write time in the
store layer (point-in-time provenance), so models intentionally do NOT set it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class NewsItem:
    ticker: str
    source: str
    published_at: datetime
    headline: str
    url: str
    sentiment: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "headline": self.headline,
            "url": self.url,
            "sentiment": self.sentiment,
            "raw": self.raw,
        }


@dataclass
class Filing:
    ticker: str
    form_type: str
    filed_at: datetime
    url: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "form_type": self.form_type,
            "filed_at": self.filed_at.isoformat(),
            "url": self.url,
            "raw": self.raw,
        }


@dataclass
class EarningsDate:
    ticker: str
    report_date: date
    confirmed: bool

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_date": self.report_date.isoformat(),
            "confirmed": self.confirmed,
        }


@dataclass
class Estimate:
    ticker: str
    period: str
    eps_est: float | None
    rev_est: float | None
    eps_actual: float | None
    surprise_pct: float | None
    as_of: date

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "period": self.period,
            "eps_est": self.eps_est,
            "rev_est": self.rev_est,
            "eps_actual": self.eps_actual,
            "surprise_pct": self.surprise_pct,
            "as_of": self.as_of.isoformat(),
        }


@dataclass
class PriceBar:
    ticker: str
    d: date
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "date": self.d.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
