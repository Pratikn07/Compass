from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.loader import PointInTimeDataset
from prescient.edge.models import OptionQuote


def load_option_quotes_for_events(
    adapter: Any,
    *,
    events: Sequence[EarningsAnnouncement],
    as_of_prices: dict[tuple[str, date], tuple[date, float]],
    max_expiration_days: int,
) -> dict[str, list[OptionQuote]]:
    """Fetch the as-of ATM straddle per event via the historical reader; accumulate per
    ticker. Events without a known as-of price are skipped; a failed fetch is skipped
    (skip-not-guess), never zero-filled."""
    out: dict[str, list[OptionQuote]] = {}
    for event in events:
        key = (event.ticker, event.report_date)
        as_of = as_of_prices.get(key)
        if as_of is None:
            continue
        as_of_date, underlying_price = as_of
        max_exp = event.report_date + timedelta(days=max_expiration_days)
        try:
            quotes = adapter.get_historical_atm_straddle(
                underlying_symbol=event.ticker,
                as_of_date=as_of_date,
                underlying_price=underlying_price,
                earnings_date=event.report_date,
                max_expiration_date=max_exp,
            )
        except Exception:  # noqa: BLE001  # intentional skip-not-guess
            continue
        if quotes:
            out.setdefault(event.ticker, []).extend(quotes)
    return out


def load_vol_ramp_straddles_for_events(
    adapter: Any,
    *,
    events: Sequence[EarningsAnnouncement],
    as_of_prices: dict[tuple[str, date], tuple[date, float]],
    bars: dict[str, list[DailyBarSnapshot]],
    entry_lead_trading_days: int,
    max_expiration_days: int,
) -> dict[tuple[str, date], list[OptionQuote]]:
    """Fetch the strike-locked vol-ramp straddle (entry call/put + exit call/put)
    per event. The entry day is the trading day `entry_lead_trading_days` bars
    before the exit as-of day, derived from the bar history (never a calendar
    subtraction, so weekends/holidays cannot shift the lead). Events with a
    missing as-of price, too little bar history, a missing entry close, or a
    failed/incomplete fetch are skipped (skip-not-guess), never zero-filled.
    Keyed by (ticker, report_date) so the assembler can thread quotes per event."""
    dataset = PointInTimeDataset(bars=bars, option_quotes={})
    out: dict[tuple[str, date], list[OptionQuote]] = {}
    for event in events:
        key = (event.ticker, event.report_date)
        as_of = as_of_prices.get(key)
        if as_of is None:
            continue
        exit_as_of_date, _ = as_of
        visible = dataset.bars_as_of(event.ticker, as_of_date=exit_as_of_date)
        if len(visible) <= entry_lead_trading_days:
            continue
        entry_bar = visible[-(entry_lead_trading_days + 1)]
        if entry_bar.close is None:
            continue
        try:
            quotes = adapter.get_historical_vol_ramp_straddle(
                underlying_symbol=event.ticker,
                entry_as_of_date=entry_bar.trading_date,
                exit_as_of_date=exit_as_of_date,
                entry_underlying_price=entry_bar.close,
                earnings_date=event.report_date,
                max_expiration_date=event.report_date
                + timedelta(days=max_expiration_days),
            )
        except Exception:  # noqa: BLE001  # intentional skip-not-guess
            continue
        if len(quotes) == 4:
            out[key] = list(quotes)
    return out
