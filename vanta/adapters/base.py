"""Adapter contract. Each adapter fetches one source for one ticker and returns
normalized records grouped into an AdapterResult. Adapters never touch the DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import EarningsDate, Estimate, Filing, NewsItem, PriceBar


@dataclass
class AdapterResult:
    news: list[NewsItem] = field(default_factory=list)
    filings: list[Filing] = field(default_factory=list)
    earnings_dates: list[EarningsDate] = field(default_factory=list)
    estimates: list[Estimate] = field(default_factory=list)
    prices: list[PriceBar] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.news) + len(self.filings) + len(self.earnings_dates)
            + len(self.estimates) + len(self.prices)
        )
