"""Backtest CLI.

  uv run python -m compass.backtest.runner calibrate
  uv run python -m compass.backtest.runner develop --hypothesis h1|h2|h3
  uv run python -m compass.backtest.runner sweep --hypothesis h1|h2|h3
  uv run python -m compass.backtest.runner validate --hypothesis h1 --i-understand-one-shot

Every run writes docs/results/<date>-<name>.json (best-effort) and prints a
human-readable scorecard. `validate` enforces the one-shot rule in code: it
refuses to run if a validation result file already exists for the hypothesis.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from ..config import REPO_ROOT
from ..ingest import DEV_END, FUNDAMENTALS_GATE, expected_quarters
from ..universe import MEMBERS, THEMES, active_members
from .calendar import TradingCalendar
from .h1_trend import (
    build_eval_dates,
    judge_h1,
    monthly_closes,
    run_timing,
    sma_daily_signal,
    sma_monthly_signal,
)
from .h2_reality import run_h2
from .h3_laggard import run_h3
from .loader import Market, load_market
from .series import Series, theme_index

RESULTS_DIR = REPO_ROOT / "docs" / "results"

DEV_START = date(2006, 1, 1)
VALIDATION_START = date(2020, 1, 1)
FABER_START = date(1990, 1, 1)
FABER_END = date(2012, 12, 31)

H1_INSTRUMENTS_PRIMARY = ["SMH", "IGV", "CIBR", "XLV", "JETS", "XLF", "XLE", "XLY"]
H1_BASKET_THEMES = ["ai-memory-storage", "data-centers-power"]


def _write_result(name: str, payload: dict) -> None:
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"{date.today().isoformat()}-{name}.json"
        path.write_text(json.dumps(payload, indent=2))
        print(f"\nresult written: {path.relative_to(REPO_ROOT)}")
    except OSError as exc:
        print(f"\n[warn] could not write result file ({exc}); JSON follows:")
        print(json.dumps(payload, indent=2))


def _fmt_pct(x: float | None) -> str:
    return f"{x:8.2%}" if x is not None else "     n/a"


def _print_timing(name: str, label: str, result) -> None:
    s, b = result.strategy, result.buy_and_hold
    print(f"\n  {name} ({label})  invested {result.months_invested}/{result.months_total} months")
    print(f"    {'':12s}  {'CAGR':>8s}  {'Sharpe':>7s}  {'MaxDD':>8s}")
    sh = f"{s.sharpe:7.2f}" if s.sharpe is not None else "    n/a"
    bh = f"{b.sharpe:7.2f}" if b.sharpe is not None else "    n/a"
    print(f"    {'timing':12s}  {_fmt_pct(s.cagr)}  {sh}  {_fmt_pct(s.max_drawdown)}")
    print(f"    {'buy-and-hold':12s}  {_fmt_pct(b.cagr)}  {bh}  {_fmt_pct(b.max_drawdown)}")


def _theme_indexes(
    market: Market, cal: TradingCalendar, start: date, end: date
) -> dict[str, Series]:
    out: dict[str, Series] = {}
    for theme in THEMES:
        out[theme.slug] = theme_index(
            market.prices,
            lambda d, slug=theme.slug: [m.ticker for m in active_members(slug, d)],
            cal.days,
            start,
            end,
        )
    return out


def _fundamentals_gate(market: Market) -> None:
    """Refuse H2/H3 runs while the fundamentals backfill is materially
    incomplete (the AV 25-req/day reality)."""
    expected = 0
    covered = 0
    missing: list[str] = []
    for m in MEMBERS:
        m_start = max(m.member_since, DEV_START)
        if m_start >= DEV_END:
            continue
        expected += expected_quarters(m_start, DEV_END)
        rows = [
            r for r in market.fundamentals.get(m.ticker, [])
            if r.report_date is not None and r.revenue is not None
            and m_start <= r.fiscal_quarter_end <= DEV_END
        ]
        covered += len(rows)
        if not market.fundamentals.get(m.ticker):
            missing.append(m.ticker)
    pct = covered / expected if expected else 0.0
    if pct < FUNDAMENTALS_GATE:
        sys.exit(
            f"fundamentals coverage is {pct:.1%} of member-quarters in the development "
            f"window (< {FUNDAMENTALS_GATE:.0%} gate). Not judging H2/H3 on missing data.\n"
            f"tickers with no fundamentals yet ({len(missing)}): {', '.join(missing)}\n"
            f"resume with: uv run python -m compass.ingest backfill --source fundamentals"
        )


def cmd_calibrate(market: Market) -> None:
    """Rulebook §5.1: reproduce Faber (2007) 10-month SMA timing on SPY,
    1990-2012 (SPY exists from 1993), pre-tax. Acceptance: CAGR within
    +/-1.5pts of buy-and-hold AND maxDD <= 60% of buy-and-hold's."""
    cal = market.calendar()
    spy = market.prices["SPY"]
    mc = monthly_closes(spy, cal)
    result = run_timing(
        instrument=spy, cal=cal, signal=sma_monthly_signal(mc, 10),
        start=FABER_START, end=FABER_END, taxed=False, name="faber-spy",
    )
    if result is None:
        sys.exit("calibration could not run — SPY data missing?")
    s, b = result.strategy, result.buy_and_hold
    cagr_ok = s.cagr is not None and b.cagr is not None and abs(s.cagr - b.cagr) <= 0.015
    dd_ok = (
        s.max_drawdown is not None and b.max_drawdown is not None
        and abs(s.max_drawdown) <= 0.60 * abs(b.max_drawdown)
    )
    passed = cagr_ok and dd_ok
    print("== Faber calibration (10-month SMA, SPY, pre-tax) ==")
    _print_timing("SPY", "calibration", result)
    print(f"\n  CAGR within 1.5pts: {cagr_ok}   maxDD <= 60% of B&H: {dd_ok}")
    print(f"  REFEREE {'CALIBRATED — verdicts count' if passed else 'BROKEN — judge nothing'}")
    _write_result("faber-calibration", {
        "window": [str(s.start), str(s.end)],
        "strategy": s.to_dict(), "buy_and_hold": b.to_dict(),
        "cagr_within_1_5pts": cagr_ok, "maxdd_le_60pct": dd_ok, "passed": passed,
    })
    if not passed:
        sys.exit(1)


def _h1_run(market: Market, cal: TradingCalendar, start: date, end: date,
            n: int, frequency: str) -> list:
    indexes = _theme_indexes(market, cal, date(2004, 1, 1), end)
    verdicts = []
    for ticker in H1_INSTRUMENTS_PRIMARY:
        prices = market.prices.get(ticker)
        if prices is None:
            continue
        result = run_timing(
            instrument=prices, cal=cal, signal=sma_daily_signal(prices, n),
            start=start, end=end, cash=market.prices.get("BIL"), taxed=True,
            eval_dates=build_eval_dates(cal, start, end, frequency), name=ticker,
        )
        if result is not None:
            verdicts.append(judge_h1(ticker, "etf-primary", result))
    for slug in H1_BASKET_THEMES:
        idx = indexes[slug]
        result = run_timing(
            instrument=idx, cal=cal, signal=sma_daily_signal(idx, n),
            start=start, end=end, cash=market.prices.get("BIL"), taxed=True,
            eval_dates=build_eval_dates(cal, start, end, frequency), name=slug,
        )
        if result is not None:
            verdicts.append(judge_h1(slug, "hindsight-curated", result))
    return verdicts


def _h1_report(verdicts: list, window_name: str, n: int, frequency: str) -> dict:
    print(f"\n== H1 theme trend — {window_name}, SMA({n}), {frequency} ==")
    survived_primary = []
    for v in verdicts:
        _print_timing(v.instrument, v.label, v.result)
        print(f"    bars: sharpe>{v.bar1_sharpe}  dd25%<{v.bar2_drawdown}  "
              f"cagr-1pt {v.bar3_cagr}  -> survived={v.survived_development}")
        if v.label == "etf-primary" and v.survived_development:
            survived_primary.append(v.instrument)
    n_primary = sum(1 for v in verdicts if v.label == "etf-primary")
    print(f"\n  primary ETFs surviving development bars: "
          f"{len(survived_primary)}/{n_primary} {survived_primary}")
    return {
        "window": window_name, "sma_n": n, "frequency": frequency,
        "verdicts": [v.to_dict() for v in verdicts],
        "primary_survivors": survived_primary,
    }


def cmd_develop(market: Market, hypothesis: str) -> None:
    cal = market.calendar()
    if hypothesis == "h1":
        verdicts = _h1_run(market, cal, DEV_START, DEV_END, 200, "monthly")
        payload = _h1_report(verdicts, "development", 200, "monthly")
        _write_result("h1-development", payload)
        return

    _fundamentals_gate(market)
    indexes = _theme_indexes(market, cal, date(2004, 1, 1), DEV_END)
    if hypothesis == "h2":
        for horizon in (63, 126):
            r = run_h2(
                market=market, themes=THEMES, active_members_fn=active_members,
                theme_indexes=indexes, cal=cal, start=DEV_START, end=DEV_END,
                horizon_bars=horizon,
            )
            _print_h2(r, f"development {horizon}d")
            _write_result(f"h2-development-{horizon}d", r.to_dict())
    elif hypothesis == "h3":
        r = run_h3(
            market=market, themes=THEMES, active_members_fn=active_members,
            theme_indexes=indexes, cal=cal, start=DEV_START, end=DEV_END,
        )
        _print_h3(r, "development")
        _write_result("h3-development", r.to_dict())


def _print_h2(r, window_name: str) -> None:
    print(f"\n== H2 financial reality — {window_name} ==")
    print(f"  quarters: {r.n_quarters} ({r.sample})")
    print(f"  top {_fmt_pct(r.top_mean)}  middle {_fmt_pct(r.middle_mean)}  "
          f"bottom {_fmt_pct(r.bottom_mean)}  all {_fmt_pct(r.all_themes_mean)}")
    print(f"  spread (annualized): {_fmt_pct(r.spread_annualized)}  "
          f"monotonic: {r.monotonic}")
    print(f"  -> survived={r.survived_development}")


def _print_h3(r, window_name: str) -> None:
    print(f"\n== H3 laggard radar — {window_name} ==")
    print(f"  trades: {r.n_trades} ({r.sample})")
    print(f"  mean excess {_fmt_pct(r.mean_excess)}  median excess {_fmt_pct(r.median_excess)}")
    ci = f"[{r.ci_95[0]:.2%}, {r.ci_95[1]:.2%}]" if r.ci_95 else "n/a"
    base = f"{r.base_rate:.1%}" if r.base_rate is not None else "n/a"
    print(f"  base rate {base}  95% CI {ci}")
    print(f"  -> survived={r.survived_development}")


def cmd_sweep(market: Market, hypothesis: str) -> None:
    """Robustness only (rulebook §5.5) — run AFTER the development verdict."""
    cal = market.calendar()
    if hypothesis == "h1":
        rows = []
        for n in (150, 175, 200, 225, 250):
            verdicts = _h1_run(market, cal, DEV_START, DEV_END, n, "monthly")
            survivors = [v.instrument for v in verdicts
                         if v.label == "etf-primary" and v.survived_development]
            n_primary = sum(1 for v in verdicts if v.label == "etf-primary")
            rows.append({"sma_n": n, "frequency": "monthly",
                         "primary_survivors": survivors, "n_primary": n_primary})
            print(f"  SMA({n}) monthly: {len(survivors)}/{n_primary} {survivors}")
        verdicts = _h1_run(market, cal, DEV_START, DEV_END, 200, "weekly")
        survivors = [v.instrument for v in verdicts
                     if v.label == "etf-primary" and v.survived_development]
        n_primary = sum(1 for v in verdicts if v.label == "etf-primary")
        rows.append({"sma_n": 200, "frequency": "weekly",
                     "primary_survivors": survivors, "n_primary": n_primary})
        print(f"  SMA(200) weekly:  {len(survivors)}/{n_primary} {survivors}")
        _write_result("h1-sensitivity", {"grid": rows})
        return

    _fundamentals_gate(market)
    indexes = _theme_indexes(market, cal, date(2004, 1, 1), DEV_END)
    if hypothesis == "h2":
        rows = []
        for horizon in (63, 126):
            for use_median in (True, False):
                r = run_h2(
                    market=market, themes=THEMES, active_members_fn=active_members,
                    theme_indexes=indexes, cal=cal, start=DEV_START, end=DEV_END,
                    horizon_bars=horizon, use_median_member=use_median,
                )
                agg = "median" if use_median else "mean"
                rows.append({"horizon": horizon, "aggregation": agg,
                             "spread_annualized": r.spread_annualized,
                             "monotonic": r.monotonic,
                             "survived": r.survived_development})
                print(f"  {horizon}d {agg}: spread {_fmt_pct(r.spread_annualized)} "
                      f"monotonic={r.monotonic} survived={r.survived_development}")
        _write_result("h2-sensitivity", {"grid": rows})
    elif hypothesis == "h3":
        rows = []
        for lookback in (60, 90, 120):
            for gap in (0.20, 0.25, 0.30):
                for hold in (63, 126):
                    r = run_h3(
                        market=market, themes=THEMES, active_members_fn=active_members,
                        theme_indexes=indexes, cal=cal, start=DEV_START, end=DEV_END,
                        lookback=lookback, gap=gap, hold_bars=hold,
                    )
                    rows.append({"lookback": lookback, "gap": gap, "hold": hold,
                                 "n": r.n_trades, "mean_excess": r.mean_excess,
                                 "base_rate": r.base_rate,
                                 "survived": r.survived_development})
                    print(f"  lb{lookback} gap{int(gap*100)} hold{hold}: "
                          f"n={r.n_trades} mean={_fmt_pct(r.mean_excess)} "
                          f"survived={r.survived_development}")
        _write_result("h3-sensitivity", {"grid": rows})


def cmd_validate(market: Market, hypothesis: str, acknowledged: bool) -> None:
    if not acknowledged:
        sys.exit("validation is ONE-SHOT (rulebook §5.3). Re-run with "
                 "--i-understand-one-shot after the owner's explicit go-ahead.")
    existing = list(RESULTS_DIR.glob(f"*-{hypothesis}-validation*.json"))
    if existing:
        sys.exit(f"REFUSED: validation already ran for {hypothesis} "
                 f"({existing[0].name}). The verdict stands (rulebook §5.3).")
    cal = market.calendar()
    end = market.prices["SPY"].dates[-1]
    if hypothesis == "h1":
        verdicts = _h1_run(market, cal, VALIDATION_START, end, 200, "monthly")
        payload = _h1_report(verdicts, "validation", 200, "monthly")
        _write_result("h1-validation", payload)
        return
    _fundamentals_gate(market)
    indexes = _theme_indexes(market, cal, date(2018, 1, 1), end)
    if hypothesis == "h2":
        for horizon in (63, 126):
            r = run_h2(
                market=market, themes=THEMES, active_members_fn=active_members,
                theme_indexes=indexes, cal=cal, start=VALIDATION_START, end=end,
                horizon_bars=horizon,
            )
            _print_h2(r, f"validation {horizon}d")
            _write_result(f"h2-validation-{horizon}d", r.to_dict())
    elif hypothesis == "h3":
        r = run_h3(
            market=market, themes=THEMES, active_members_fn=active_members,
            theme_indexes=indexes, cal=cal, start=VALIDATION_START, end=end,
        )
        _print_h3(r, "validation")
        _write_result("h3-validation", r.to_dict())


def main() -> None:
    parser = argparse.ArgumentParser(prog="compass.backtest.runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("calibrate")
    for name in ("develop", "sweep"):
        p = sub.add_parser(name)
        p.add_argument("--hypothesis", choices=["h1", "h2", "h3"], required=True)
    pv = sub.add_parser("validate")
    pv.add_argument("--hypothesis", choices=["h1", "h2", "h3"], required=True)
    pv.add_argument("--i-understand-one-shot", action="store_true")
    parser.add_argument("--refresh-snapshot", action="store_true")
    args = parser.parse_args()

    market = load_market(refresh=getattr(args, "refresh_snapshot", False))
    if args.command == "calibrate":
        cmd_calibrate(market)
    elif args.command == "develop":
        cmd_develop(market, args.hypothesis)
    elif args.command == "sweep":
        cmd_sweep(market, args.hypothesis)
    elif args.command == "validate":
        cmd_validate(market, args.hypothesis, args.i_understand_one_shot)


if __name__ == "__main__":
    main()
