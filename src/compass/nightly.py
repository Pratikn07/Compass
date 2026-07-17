"""The nightly brain (Phase 3, Scenario B).

  uv run python -m compass.nightly [--date YYYY-MM-DD]

Single-run, cron-compatible, idempotent (running twice for the same date
changes nothing — all writes are keyed upserts). Order:

  1. prices delta append (Sunday: full refetch -> adjustment restatements)
  2. fundamentals refresh (EDGAR for due reporters; AV enrichment until cap)
  3. theme states (reusing the SAME modules the harness validated)
  4. recommendations — H2 quarterly ranking on quarter-end+1; an explicit
     "nothing to do" row on every other day
  5. self-check (stale data -> alert rows the API surfaces)

Propose-only is structural: this module cannot place, size, or authorize
anything; there is no broker import anywhere in this package.
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from .backtest.calendar import TradingCalendar
from .backtest.h2_reality import quarter_ends, terciles, theme_scores
from .backtest.loader import Market, load_market
from .backtest.series import Series, sma_at, theme_index
from .cache import JsonFileCache
from .jobs.nightly import NightlyRunResult, StepResult, run_nightly
from .providers import alpha_vantage as alphavantage
from .providers import sec_edgar as edgar
from .providers import yahoo
from .research.weekly import run_weekly_edge_report
from .store import Store, make_warehouse
from .universe import MEMBERS, THEMES, active_members, all_tickers

# Recorded H2 evidence (sources: docs/results/2026-06-10-h2-development-126d.json
# and docs/results/2026-06-11-h2-validation-126d.json). The edge is in average
# MAGNITUDE (+4.2%/yr dev spread), not per-quarter consistency — shown honestly.
H2_EVIDENCE = {
    "horizon_bars": 126,
    "dev_spread_annualized": 0.042,
    "dev_top_beats_bottom": "20/41 quarters (48.8%)",
    "validation_top_beats_bottom": "14/23 quarters (60.9%)",
    "combined_base_rate": 34 / 64,
    "claim": (
        "themes ranked top-tercile by reported fundamentals beat bottom-tercile "
        "theme baskets over the next ~6 months on average; the edge is in average "
        "magnitude, not per-quarter consistency"
    ),
    "source": "h2 development 2026-06-10 + one-shot validation 2026-06-11",
}

STALE_PRICE_ALERT_DAYS = 5
EDGAR_DUE_AFTER_DAYS = 95
EDGAR_NIGHTLY_CAP = 20


# ---------- step 1: prices ----------

def latest_bar_dates(store: Store) -> dict[str, date]:
    """One tiny indexed query per ticker — NOT a full-table pull (the naive
    version paged 536k rows and took an hour; found on the first real run)."""
    out: dict[str, date] = {}
    for ticker in all_tickers():
        rows = (
            store.select("price_bars", "d").eq("ticker", ticker)
            .order("d", desc=True).limit(1).execute()
        ).data
        if rows:
            out[ticker] = date.fromisoformat(rows[0]["d"])
    return out


def prices_delta(
    store: Store,
    http: httpx.Client,
    today: date,
    errors: list[str] | None = None,
) -> int:
    last = latest_bar_dates(store)
    full_refresh = today.weekday() == 6  # Sunday: pick up restatements
    written = 0
    for ticker in all_tickers():
        try:
            if full_refresh or ticker not in last:
                bars = yahoo.fetch_daily_bars_fresh(ticker, http, start=date(1990, 1, 1))
            else:
                start = last[ticker] - timedelta(days=7)  # overlap heals gaps
                bars = yahoo.fetch_daily_bars_fresh(ticker, http, start=start)
            written += store.upsert_price_bars(bars)
        except Exception as exc:  # noqa: BLE001 — log and continue
            if errors is not None:
                errors.append(f"{ticker}:{exc.__class__.__name__}")
    return written


# ---------- step 2: fundamentals ----------

def fundamentals_refresh(
    store: Store,
    cache: JsonFileCache,
    http: httpx.Client,
    today: date,
    errors: list[str] | None = None,
) -> int:
    rows = store.fetch_all("fundamentals", "ticker,fiscal_quarter_end")
    newest: dict[str, date] = {}
    written = 0
    for r in rows:
        d = date.fromisoformat(r["fiscal_quarter_end"])
        if r["ticker"] not in newest or d > newest[r["ticker"]]:
            newest[r["ticker"]] = d

    # EDGAR: members whose newest stored quarter is old enough that a new
    # report is likely filed.
    cik_map = edgar.fetch_ticker_cik_map(cache, http)
    due = [
        m.ticker for m in MEMBERS
        if (today - newest.get(m.ticker, date(1900, 1, 1))).days > EDGAR_DUE_AFTER_DAYS
        and m.ticker in cik_map
    ][:EDGAR_NIGHTLY_CAP]
    for ticker in due:
        try:
            fresh_rows = edgar.fetch_fundamentals(
                ticker, cik_map[ticker], cache, http, fresh=True
            )
            written += store.upsert_fundamentals(fresh_rows)
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"edgar:{ticker}:{exc.__class__.__name__}")

    # Alpha Vantage enrichment (EPS estimates/surprise) continues until the
    # daily cap; cached tickers cost nothing.
    for m in MEMBERS:
        try:
            av_rows = alphavantage.fetch_fundamentals(m.ticker, cache, http)
            written += store.upsert_fundamentals(av_rows)
        except alphavantage.RateLimited:
            if errors is not None:
                errors.append("alpha_vantage:rate_limited")
            break
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"alpha_vantage:{m.ticker}:{exc.__class__.__name__}")
    return written


# ---------- step 3: theme states (pure builder + writer) ----------

def build_theme_state_row(
    slug: str, idx: Series, on: date, prev: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Pure: one day's state row from the theme index. Parity-tested against
    the harness's own series math (it IS the harness's series math)."""
    level = idx.value_on_or_before(on)
    if level is None:
        return None
    sma = sma_at(idx, on, 200)
    trend_on = (level > sma) if sma is not None else None
    days = 1
    if prev is not None and prev.get("trend_on") == trend_on and trend_on is not None:
        days = int(prev.get("days_in_state", 0)) + 1
    return {
        "d": on.isoformat(),
        "theme_slug": slug,
        "index_level": level,
        "sma200": sma,
        "trend_on": trend_on,
        "days_in_state": days,
    }


def theme_states(market: Market, store: Store, today: date) -> tuple[date, dict[str, Series]]:
    cal = market.calendar()
    last_trading = max(d for d in cal.days if d <= today)
    indexes: dict[str, Series] = {}
    rows: list[dict[str, Any]] = []
    for theme in THEMES:
        idx = theme_index(
            market.prices,
            lambda d, slug=theme.slug: [m.ticker for m in active_members(slug, d)],
            cal.days,
            date(2004, 1, 1),
            last_trading,
        )
        indexes[theme.slug] = idx
        prev_rows = (
            store.select("theme_state_daily", "trend_on,days_in_state")
            .eq("theme_slug", theme.slug)
            .lt("d", last_trading.isoformat())
            .order("d", desc=True)
            .limit(1)
            .execute()
        ).data
        row = build_theme_state_row(
            theme.slug, idx, last_trading, prev_rows[0] if prev_rows else None
        )
        if row is not None:
            rows.append(row)
    store.upsert_rows(
        "theme_state_daily",
        rows,
        on_conflict="owner_id,d,theme_slug",
    )
    return last_trading, indexes


# ---------- step 4: recommendations ----------

def build_recommendations(
    market: Market, cal: TradingCalendar, on: date
) -> list[dict[str, Any]]:
    """Pure: the day's recommendation rows. H2 ranking only on the first
    trading day after a calendar quarter end; an explicit none-row otherwise."""
    qs = quarter_ends(date(on.year - 1, 1, 1), on)
    last_q = qs[-1] if qs else None
    ranking_day = last_q is not None and cal.next_day(last_q) == on
    if not ranking_day:
        return [{
            "d": on.isoformat(), "hypothesis": "none", "instrument": "-",
            "action": "none",
            "reasoning": {"note": "nothing to do today", "next_ranking_after": (
                quarter_ends(on, date(on.year + 1, 12, 31))[0].isoformat()
                if quarter_ends(on, date(on.year + 1, 12, 31)) else None
            )},
            "base_rate": None,
        }]

    scores = theme_scores(market, THEMES, active_members, on)
    scored = sorted(
        [(slug, s) for slug, s in scores.items() if s is not None],
        key=lambda x: x[1], reverse=True,
    )
    ranked = [slug for slug, _ in scored]
    top, mid, bot = terciles(ranked)
    etf_by_slug = {t.slug: t.etf_ticker for t in THEMES}
    rows = []
    for i, (slug, score) in enumerate(scored, 1):
        tercile = "top" if slug in top else ("bottom" if slug in bot else "middle")
        action = {"top": "consider_enter", "bottom": "consider_exit"}.get(tercile, "none")
        rows.append({
            "d": on.isoformat(), "hypothesis": "h2", "instrument": slug,
            "action": action,
            "reasoning": {
                "as_of_quarter_end": last_q.isoformat(),
                "rank": i, "of": len(scored), "tercile": tercile,
                "theme_score": score,
                "etf": etf_by_slug.get(slug),
                **H2_EVIDENCE,
            },
            "base_rate": H2_EVIDENCE["combined_base_rate"] if action != "none" else None,
        })
    return rows


def recommendations(
    market: Market,
    store: Store,
    on: date,
    *,
    run_id: str | None = None,
) -> int:
    cal = market.calendar()
    rows = build_recommendations(market, cal, on)
    return store.upsert_decisions(run_id=run_id or f"nightly:{on.isoformat()}", rows=rows)


# ---------- step 5: self-check ----------

def self_check(store: Store, today: date) -> list[str]:
    alerts: list[str] = []
    spy = (
        store.select("price_bars", "d").eq("ticker", "SPY")
        .order("d", desc=True).limit(1).execute()
    ).data
    if not spy:
        alerts.append("no SPY bars at all")
    elif (today - date.fromisoformat(spy[0]["d"])).days > STALE_PRICE_ALERT_DAYS:
        alerts.append(f"SPY prices stale: latest {spy[0]['d']}")
    state = (
        store.select("theme_state_daily", "d")
        .order("d", desc=True).limit(1).execute()
    ).data
    if not state:
        alerts.append("no theme states written yet")
    return alerts


def run(today: date | None = None) -> NightlyRunResult:
    trading_date = today or (datetime.now(UTC).date() - timedelta(days=1))
    store = make_warehouse()
    cache = JsonFileCache()
    shared: dict[str, Any] = {}

    with httpx.Client() as http:
        def seed_step(_run_id: str, _date: date) -> StepResult:
            counts = store.seed_universe()
            return StepResult(
                provider="compass",
                table_name="companies,themes,theme_memberships",
                written_record_count=sum(counts.values()),
                payload=counts,
            )

        def price_step(_run_id: str, run_date: date) -> StepResult:
            errors: list[str] = []
            written = prices_delta(store, http, run_date, errors)
            return StepResult(
                provider="yahoo",
                table_name="price_bars",
                written_record_count=written,
                error_count=len(errors),
                payload={"failures": errors},
            )

        def fundamentals_step(_run_id: str, run_date: date) -> StepResult:
            errors: list[str] = []
            written = fundamentals_refresh(store, cache, http, run_date, errors)
            return StepResult(
                provider="sec_edgar,alpha_vantage",
                table_name="fundamentals",
                written_record_count=written,
                error_count=len(errors),
                payload={"failures": errors},
            )

        def theme_state_step(_run_id: str, run_date: date) -> StepResult:
            market = load_market(refresh=True)
            last_trading, indexes = theme_states(market, store, run_date)
            shared["market"] = market
            shared["last_trading"] = last_trading
            return StepResult(
                provider="compass",
                table_name="theme_state_daily",
                written_record_count=len(indexes),
            )

        def decision_step(run_id: str, _run_date: date) -> StepResult:
            market = shared["market"]
            last_trading = shared["last_trading"]
            written = recommendations(market, store, last_trading, run_id=run_id)
            return StepResult(
                provider="compass",
                table_name="decision_records,journal_records",
                written_record_count=written,
            )

        def health_step(_run_id: str, run_date: date) -> StepResult:
            alerts = self_check(store, run_date)
            return StepResult(
                provider="compass",
                table_name="system_health",
                written_record_count=1,
                error_count=len(alerts),
                payload={"alerts": alerts},
            )

        def weekly_backtest(_run_id: str, _run_date: date) -> dict:
            return run_weekly_edge_report(store)

        return run_nightly(
            repository=store,
            trading_date=trading_date,
            steps=[
                seed_step,
                price_step,
                fundamentals_step,
                theme_state_step,
                decision_step,
                health_step,
            ],
            weekly_backtest=weekly_backtest,
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="compass.nightly")
    parser.add_argument("--date", default=None, help="override run date (YYYY-MM-DD)")
    args = parser.parse_args()
    run(date.fromisoformat(args.date) if args.date else None)


if __name__ == "__main__":
    main()
