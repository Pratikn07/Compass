from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from prescient.edge.models import OptionQuote


class OptionDepthSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    earliest_quote_date: date | None
    latest_quote_date: date | None
    quote_count: int


def summarize_option_history_depth(
    quotes_by_ticker: dict[str, list[OptionQuote]],
) -> dict[str, OptionDepthSummary]:
    """Report how far back free option-quote data reaches per ticker - answers the
    spec's open risk about free options-history depth."""
    summary: dict[str, OptionDepthSummary] = {}
    for ticker, quotes in quotes_by_ticker.items():
        dates = [q.quote_date for q in quotes]
        summary[ticker.strip().upper()] = OptionDepthSummary(
            ticker=ticker.strip().upper(),
            earliest_quote_date=min(dates) if dates else None,
            latest_quote_date=max(dates) if dates else None,
            quote_count=len(quotes),
        )
    return summary
