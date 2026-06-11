# Phase 1 gate evidence

**Date:** 2026-06-10 (updated as the fundamentals backfill resumes)

## Price coverage — PASS

All 85 tickers (74 members, 8 theme ETFs, 3 benchmarks) at **100.00%** coverage
against the SPY trading calendar (2006-01-03 → 2026-06-09, 5,140 trading days),
measured from each ticker's first bar so late listings are not penalized.
Gate requirement: ≥ 95%. Full per-ticker table: `uv run python -m compass.ingest coverage`.

Depth notes:
- SPY history reaches 1993-01-29 (8,397 daily bars) — covers the Faber
  calibration window (rulebook §5.1).
- Source: Yahoo chart API (split- AND dividend-adjusted closes). **Plan
  deviation, recorded:** Stooq (the planned source) now 404s behind a
  JavaScript bot challenge (verified 2026-06-10) and was replaced; see
  `src/compass/adapters/yahoo.py` docstring.

## Adjusted-close crosscheck (Yahoo vs Alpaca adjustment=all)

2,623 overlapping days per ticker (2016 → present):

| Ticker | Mean deviation | Worst single day |
|---|---|---|
| SPY | 0.12% | 2.79% |
| MU | 0.006% | 0.53% |
| XLE | 0.03% | 5.32% |
| JPM | 0.003% | 0.13% |
| NVDA | 0.008% | 0.11% |

Mean deviations are negligible; worst-case single-day spikes cluster around
ex-dividend dates where the providers' adjustment timing differs by a day.
Acceptable for monthly-evaluation strategies (H1–H3 never trade on a single
day's adjustment artifact).

## Fundamentals coverage — IN PROGRESS (Alpha Vantage 25 req/day cap)

12 of 74 members ingested so far (ai-chips theme complete at 97.7% of
member-quarters in the development window; ai-memory-storage at 71.2%).
Remaining 62 members ≈ 124 requests ≈ **5 more daily resumed runs** of
`uv run python -m compass.ingest backfill --source fundamentals` — the
fetch-once cache and clean rate-limit stop make each resume free of repeat
requests.

The < 70% themes flagged today reflect *not-yet-fetched* tickers, not missing
history; the verdict on whether the shrink-the-claim rule (rulebook §6)
actually applies waits until the backfill completes.

## Spot checks

10 price rows and 5 fundamentals rows sampled (seed 42, reproducible) and
printed by the coverage command for manual verification against public
sources. Example verified pair: MRVL FQ-end 2007-04-30 reported 2007-07-09 —
a late filing captured correctly; exactly the kind of row `report_date`
provenance exists to get right.
