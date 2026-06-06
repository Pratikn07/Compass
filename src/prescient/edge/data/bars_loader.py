from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from prescient.data.models import DailyBarSnapshot


def load_daily_bars(
    adapter: Any, *, tickers: Sequence[str], start: date, end: date
) -> dict[str, list[DailyBarSnapshot]]:
    """One batched multi-symbol Alpaca call for the full window."""
    return adapter.get_daily_bars(symbols=list(tickers), start=start, end=end)
