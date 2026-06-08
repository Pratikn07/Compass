"""Run the edge backtest against live data (Alpha Vantage earnings + Alpaca
bars/options). Requires ALPHAVANTAGE_API_KEY, ALPACA_API_KEY_ID,
ALPACA_API_SECRET_KEY.

Usage:
  uv run python scripts/run_edge_backtest.py --limit 20   # cheap smoke test
  uv run python scripts/run_edge_backtest.py              # full run

Caches earnings history on disk (fetch-once) under .cache/edge/.
Propose-only research tooling: it never places, sizes, or suggests a trade.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from prescient.data.alpaca_market import AlpacaMarketDataAdapter
from prescient.edge.data.assembler import as_of_price_for, assemble_edge_dataset
from prescient.edge.data.bars_loader import load_daily_bars
from prescient.edge.data.cache import JsonFileCache
from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter
from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.data.option_loader import load_option_quotes_for_events
from prescient.edge.runner import run_edge_backtest
from prescient.edge.strategy import (
    AlwaysUpStrategy,
    CoinFlipStrategy,
    ReactionAwarePeerStrategy,
    ShortVolStrategy,
)
from prescient.edge.universe import load_edge_universe
from prescient.live_data.alpaca_readers import (
    build_alpaca_sdk_readers,
    build_historical_option_reader,
)

_HORIZON_DAYS = 2
_PEER_WINDOW_DAYS = 21
_MAX_EXPIRATION_DAYS = 14


def _cached_earnings(cache, adapter, tickers, start, end, *, request_delay_s=1.0):
    """Load earnings per ticker, reusing the disk cache (fetch-once). Uncached
    tickers are fetched one at a time with a small polite delay between requests
    (handles any per-minute sub-limit); on the first rate-limit we stop fetching
    for this run rather than hammering an exhausted daily quota. Whatever is
    fetched is cached permanently, so re-running on a later day resumes where the
    quota left off until the whole universe is cached."""
    out: list[EarningsAnnouncement] = []
    rate_limited = False
    for ticker in tickers:
        cached = cache.get(f"earnings:{ticker}")
        if cached is not None:
            out.extend(
                EarningsAnnouncement(**row)
                for row in cached
                if start.isoformat() <= row["report_date"] <= end.isoformat()
            )
            continue
        if rate_limited:
            # Daily quota already exhausted this run; skip the rest (they'd just
            # return rate_limited). They stay uncached and resume on a later day.
            continue
        fetched, errors = adapter.get_earnings_history(
            tickers=[ticker], start=date(2000, 1, 1), end=end
        )
        for err in errors:
            print(f"  earnings error: {err.error_type.value} {err.symbol or ''}")
            if err.error_type.value == "rate_limited":
                rate_limited = True
        if fetched:
            cache.put(
                f"earnings:{ticker}",
                [a.model_dump(mode="json") for a in fetched],
            )
            out.extend(a for a in fetched if start <= a.report_date <= end)
        if not rate_limited:
            time.sleep(request_delay_s)
    return out


def _fmt(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "-"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap number of target events (cheap smoke test)",
    )
    parser.add_argument("--years", type=int, default=2)
    args = parser.parse_args()

    load_dotenv()
    av_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    alpaca_id = os.environ.get("ALPACA_API_KEY_ID")
    alpaca_secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not (av_key and alpaca_id and alpaca_secret):
        raise SystemExit(
            "Missing ALPHAVANTAGE_API_KEY / ALPACA_API_KEY_ID / "
            "ALPACA_API_SECRET_KEY in env."
        )

    end = date.today()
    start = end - timedelta(days=365 * args.years)

    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    tickers = universe.tickers
    print(f"Universe: {len(tickers)} tickers | window {start} -> {end}")

    cache = JsonFileCache(Path(".cache/edge"))
    av = AlphaVantageEarningsHistoryAdapter(api_key=av_key)
    announcements = _cached_earnings(cache, av, tickers, start, end)
    print(f"Earnings announcements in window: {len(announcements)}")

    option_reader, bars_reader = build_alpaca_sdk_readers(
        api_key_id=alpaca_id, api_secret_key=alpaca_secret
    )
    alpaca = AlpacaMarketDataAdapter(
        option_chain_reader=option_reader, daily_bars_reader=bars_reader
    )

    bars = load_daily_bars(alpaca, tickers=tickers, start=start, end=end)
    print(f"Tickers with bars: {len(bars)}")

    target_events = sorted(announcements, key=lambda a: a.report_date, reverse=True)
    if args.limit is not None:
        target_events = target_events[: args.limit]
        print(f"Limited to {len(target_events)} most-recent events for smoke test.")

    hist_reader = build_historical_option_reader(
        api_key_id=alpaca_id, api_secret_key=alpaca_secret
    )
    hist_adapter = AlpacaMarketDataAdapter(historical_option_reader=hist_reader)

    as_of_prices: dict[tuple[str, date], tuple[date, float]] = {}
    for event in target_events:
        priced = as_of_price_for(event.ticker, event.report_date, bars)
        if priced is not None:
            as_of_prices[(event.ticker, event.report_date)] = priced

    option_quotes = load_option_quotes_for_events(
        hist_adapter,
        events=target_events,
        as_of_prices=as_of_prices,
        max_expiration_days=_MAX_EXPIRATION_DAYS,
    )
    print(f"Tickers with option quotes: {len(option_quotes)}")

    result = assemble_edge_dataset(
        announcements=announcements,
        bars=bars,
        option_quotes=option_quotes,
        target_tickers=[a.ticker for a in target_events],
        horizon_days=_HORIZON_DAYS,
        peer_window_days=_PEER_WINDOW_DAYS,
    )
    print(
        f"\nCoverage: {len(result.event_contexts)}/{result.events_total} evaluable; "
        f"{result.events_dropped} dropped {result.drop_reasons}"
    )

    backtest = run_edge_backtest(
        contexts=result.event_contexts,
        strategies=[
            ReactionAwarePeerStrategy(),
            ShortVolStrategy(),
            CoinFlipStrategy(),
            AlwaysUpStrategy(),
        ],
    )

    print("\n=== SCORECARDS ===")
    print(
        f"{'strategy':24} {'eval':>5} {'dir%':>6} {'beat%':>6} "
        f"{'avgRet%':>8} {'medRet%':>8} {'survived':>9}"
    )
    for source, card in backtest.scorecards.items():
        print(
            f"{source:24} {card.events_evaluable:>5} "
            f"{_fmt(card.directional_hit_rate):>6} "
            f"{_fmt(card.beat_implied_rate):>6} "
            f"{_fmt(card.average_option_return_pct):>8} "
            f"{_fmt(card.median_option_return_pct):>8} {str(card.survived):>9}"
        )
        for note in card.notes:
            print(f"    note: {note}")
    peer_card = backtest.scorecards.get("reaction_aware_peer")
    if peer_card is not None:
        print(f"\nsample size: {peer_card.sample_size_verdict.value}")


if __name__ == "__main__":
    main()
