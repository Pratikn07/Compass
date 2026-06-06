from __future__ import annotations

from datetime import timedelta
from typing import Any, Sequence

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def load_option_quotes_for_events(
    adapter: Any, *, events: Sequence[EarningsAnnouncement], max_expiration_days: int
) -> dict[str, list[OptionQuote]]:
    """One ATM-chain pull per event; accumulate per ticker. A failed event is
    skipped (skip-not-guess), never zero-filled."""
    out: dict[str, list[OptionQuote]] = {}
    for event in events:
        max_exp = event.report_date + timedelta(days=max_expiration_days)
        try:
            quotes = adapter.get_atm_option_quotes(
                underlying_symbol=event.ticker,
                quote_date=event.report_date,
                earnings_date=event.report_date,
                max_expiration_date=max_exp,
            )
        except Exception:  # noqa: BLE001  # intentional skip-not-guess
            continue
        if quotes:
            out.setdefault(event.ticker, []).extend(quotes)
    return out
