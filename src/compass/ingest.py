"""Backfill and coverage CLI.

  uv run python -m compass.ingest backfill [--source prices|fundamentals|all] [--tickers ...]
  uv run python -m compass.ingest crosscheck [--tickers ...]
  uv run python -m compass.ingest coverage

Backfill is idempotent (upserts) and resumable (fetch-once cache; Alpha
Vantage throttle stops the run cleanly — re-run tomorrow, cached tickers
cost zero requests).
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date

import httpx

from .adapters import alpaca, alphavantage, edgar, yahoo
from .cache import JsonFileCache
from .config import DEVELOPMENT_START
from .store import Store, make_client
from .universe import MEMBERS, THEMES, all_tickers

DEV_END = date(2019, 12, 31)
PRICE_GATE = 0.95
FUNDAMENTALS_GATE = 0.70


def price_coverage(ticker_days: list[date], spy_days: list[date]) -> tuple[float, int, int]:
    """Coverage vs the SPY trading calendar, measured from the ticker's first
    bar (late listings aren't penalized for not existing). Returns (pct, have,
    expected)."""
    if not ticker_days or not spy_days:
        return 0.0, 0, len(spy_days)
    first = min(ticker_days)
    expected = [d for d in spy_days if d >= first]
    have = len(set(ticker_days) & set(expected))
    return (have / len(expected) if expected else 0.0), have, len(expected)


def expected_quarters(member_start: date, dev_end: date) -> int:
    """Whole quarters a member is expected to have reported in the window."""
    if member_start >= dev_end:
        return 0
    quarters = (dev_end.year - member_start.year) * 4 + (dev_end.month - member_start.month) // 3
    return max(quarters, 0)


def _selected(tickers_arg: list[str] | None) -> list[str]:
    universe = all_tickers()
    if not tickers_arg:
        return universe
    unknown = sorted(set(tickers_arg) - set(universe))
    if unknown:
        sys.exit(f"unknown tickers (not in universe): {', '.join(unknown)}")
    return tickers_arg


def backfill(source: str, tickers_arg: list[str] | None) -> None:
    store = Store(make_client())
    cache = JsonFileCache()
    tickers = _selected(tickers_arg)

    seeded = store.seed_universe()
    print(f"seeded universe: {seeded}")

    member_tickers = {m.ticker for m in MEMBERS}

    with httpx.Client() as client:
        if source in ("prices", "all"):
            for i, ticker in enumerate(tickers, 1):
                try:
                    bars = yahoo.fetch_daily_bars(ticker, cache, client)
                    n = store.upsert_price_bars(bars)
                    store.log_run(source="yahoo", ticker=ticker, records=n, status="ok")
                    first = bars[0].d if bars else "-"
                    print(f"[{i}/{len(tickers)}] {ticker}: {n} bars (from {first})")
                except Exception as exc:  # noqa: BLE001 — log and continue, skip-don't-guess
                    store.log_run(
                        source="yahoo", ticker=ticker, records=0,
                        status="error", error=str(exc)[:500],
                    )
                    print(f"[{i}/{len(tickers)}] {ticker}: ERROR {exc}")
                time.sleep(0.3)  # politeness; cached re-runs skip this loop's fetches

        if source == "fundamentals-edgar":
            # Official, key-less SEC source covering members Alpha Vantage
            # hasn't reached. Tickers with existing rows are skipped so AV's
            # richer rows (EPS surprise) are never clobbered by EDGAR's.
            have = {
                r["ticker"]
                for r in _fetch_all(store.client, "compass_fundamentals", "ticker")
            }
            cik_map = edgar.fetch_ticker_cik_map(cache, client)
            todo = [t for t in tickers if t in member_tickers and t not in have]
            for i, ticker in enumerate(todo, 1):
                cik = cik_map.get(ticker)
                if cik is None:
                    print(f"[{i}/{len(todo)}] {ticker}: no CIK (skipped)")
                    continue
                try:
                    rows = edgar.fetch_fundamentals(ticker, cik, cache, client)
                    n = store.upsert_fundamentals(rows)
                    store.log_run(source="edgar", ticker=ticker, records=n, status="ok")
                    print(f"[{i}/{len(todo)}] {ticker}: {n} quarters")
                except Exception as exc:  # noqa: BLE001
                    store.log_run(
                        source="edgar", ticker=ticker, records=0,
                        status="error", error=str(exc)[:500],
                    )
                    print(f"[{i}/{len(todo)}] {ticker}: ERROR {exc}")

        if source in ("fundamentals", "all"):
            fund_tickers = [t for t in tickers if t in member_tickers]
            for i, ticker in enumerate(fund_tickers, 1):
                try:
                    rows = alphavantage.fetch_fundamentals(ticker, cache, client)
                    n = store.upsert_fundamentals(rows)
                    store.log_run(source="alphavantage", ticker=ticker, records=n, status="ok")
                    print(f"[{i}/{len(fund_tickers)}] {ticker}: {n} quarters")
                except alphavantage.RateLimited as exc:
                    print(f"[{i}/{len(fund_tickers)}] {ticker}: RATE LIMITED — stopping "
                          f"fundamentals cleanly. Re-run tomorrow (cache resumes). {exc}")
                    break
                except Exception as exc:  # noqa: BLE001
                    store.log_run(
                        source="alphavantage", ticker=ticker, records=0,
                        status="error", error=str(exc)[:500],
                    )
                    print(f"[{i}/{len(fund_tickers)}] {ticker}: ERROR {exc}")


def crosscheck(tickers_arg: list[str] | None) -> None:
    """Compare Yahoo adj_close vs Alpaca (adjustment=all) on the overlap window.

    Report-only: nothing is stored. Quantifies the Yahoo adjustment quality."""
    cache = JsonFileCache()
    tickers = tickers_arg or ["SPY", "MU", "XLE", "JPM", "NVDA"]
    with httpx.Client() as client:
        for ticker in tickers:
            y = {b.d: b.adj_close for b in yahoo.fetch_daily_bars(ticker, cache, client)}
            a = {b.d: b.adj_close for b in alpaca.fetch_daily_bars(ticker, cache, client)}
            overlap = sorted(set(y) & set(a))
            if not overlap:
                print(f"{ticker}: no overlap")
                continue
            diffs = [abs(y[d] - a[d]) / a[d] for d in overlap if a[d]]
            worst = max(diffs)
            mean = sum(diffs) / len(diffs)
            print(f"{ticker}: {len(overlap)} overlap days | mean dev {mean:.4%} | "
                  f"worst {worst:.4%}")


def _fetch_all(client, table: str, columns: str, page_size: int = 1000) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            client.table(table).select(columns).range(start, start + page_size - 1).execute()
        ).data
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def coverage() -> None:
    client = make_client()
    dev_start = date.fromisoformat(DEVELOPMENT_START)

    print("loading price bars (ticker, d) ...")
    bars = _fetch_all(client, "compass_price_bars", "ticker,d")
    by_ticker: dict[str, list[date]] = {}
    for row in bars:
        by_ticker.setdefault(row["ticker"], []).append(date.fromisoformat(row["d"]))

    spy_days = sorted(d for d in by_ticker.get("SPY", []) if d >= dev_start)
    if not spy_days:
        sys.exit("no SPY bars ingested — run backfill first (SPY is the trading calendar)")

    print(f"\n== Price coverage vs SPY calendar ({dev_start} -> {spy_days[-1]}, "
          f"{len(spy_days)} trading days) ==")
    failures = []
    for ticker in sorted(by_ticker):
        days = sorted(d for d in by_ticker[ticker] if d >= dev_start)
        if not days:
            failures.append(ticker)
            print(f"  {ticker:6s}  NO DATA in window")
            continue
        pct, have, expected = price_coverage(days, spy_days)
        flag = "" if pct >= PRICE_GATE else "  <-- BELOW 95% GATE"
        if pct < PRICE_GATE:
            failures.append(ticker)
        print(f"  {ticker:6s}  {pct:7.2%}  ({have}/{expected} days, from {days[0]}){flag}")

    missing = sorted(set(all_tickers()) - set(by_ticker))
    if missing:
        failures.extend(missing)
        print(f"  not ingested at all: {', '.join(missing)}")

    print("\n== Fundamentals coverage (development window "
          f"{dev_start} -> {DEV_END}, member-quarters) ==")
    fundamentals = _fetch_all(
        client, "compass_fundamentals", "ticker,fiscal_quarter_end,report_date,revenue"
    )
    fq: dict[str, list[dict]] = {}
    for row in fundamentals:
        fq.setdefault(row["ticker"], []).append(row)

    overall_expected = 0
    overall_covered = 0
    for theme in THEMES:
        expected = 0
        covered = 0
        for m in [m for m in MEMBERS if m.theme_slug == theme.slug]:
            m_start = max(m.member_since, dev_start)
            if m_start >= DEV_END:
                continue
            expected += expected_quarters(m_start, DEV_END)
            rows = fq.get(m.ticker, [])
            covered += sum(
                1 for r in rows
                if r["report_date"] is not None and r["revenue"] is not None
                and m_start <= date.fromisoformat(r["fiscal_quarter_end"]) <= DEV_END
            )
        pct = covered / expected if expected else 0.0
        flag = "" if pct >= FUNDAMENTALS_GATE else "  <-- below 70%, shrink-the-claim applies"
        print(f"  {theme.slug:20s}  {pct:7.2%}  ({covered}/{expected} member-quarters){flag}")
        overall_expected += expected
        overall_covered += covered

    pct = overall_covered / overall_expected if overall_expected else 0.0
    print(f"  {'TOTAL':20s}  {pct:7.2%}  ({overall_covered}/{overall_expected})")

    print("\n== Spot checks (verify manually against public sources) ==")
    rng = random.Random(42)  # reproducible spot-check sample
    price_sample = rng.sample(bars, min(10, len(bars)))
    for row in price_sample:
        print(f"  price  {row['ticker']:6s} {row['d']}   "
              f"https://finance.yahoo.com/quote/{row['ticker']}/history")
    if fundamentals:
        for row in rng.sample(fundamentals, min(5, len(fundamentals))):
            print(f"  fund   {row['ticker']:6s} FQ-end {row['fiscal_quarter_end']} "
                  f"reported {row['report_date']} revenue {row['revenue']}")

    print("\n== Gate verdict ==")
    if failures:
        print(f"  price gate: FAIL ({len(failures)} tickers below 95% or missing): "
              f"{', '.join(failures)}")
    else:
        print("  price gate: PASS (all tickers >= 95%)")
    print("  fundamentals: recorded above (informational gate; <70% triggers shrink-the-claim)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="compass.ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backfill = sub.add_parser("backfill", help="seed universe and ingest data")
    p_backfill.add_argument(
        "--source",
        choices=["prices", "fundamentals", "fundamentals-edgar", "all"],
        default="all",
    )
    p_backfill.add_argument("--tickers", nargs="*", default=None)

    p_cross = sub.add_parser("crosscheck", help="Yahoo vs Alpaca adjusted-close comparison")
    p_cross.add_argument("--tickers", nargs="*", default=None)

    sub.add_parser("coverage", help="gate evidence: price/fundamentals coverage + spot checks")

    args = parser.parse_args()
    if args.command == "backfill":
        backfill(args.source, args.tickers)
    elif args.command == "crosscheck":
        crosscheck(args.tickers)
    elif args.command == "coverage":
        coverage()


if __name__ == "__main__":
    main()
