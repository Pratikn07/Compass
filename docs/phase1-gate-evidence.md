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

## Fundamentals coverage — GATE LIFTED 2026-06-11 (75.97% total)

The Alpha Vantage-only path (25 req/day) was projected at ~5 more days; by
owner decision (2026-06-11) the **SEC EDGAR companyfacts API** was added as a
fundamentals source (official, free, key-less, filing-date-stamped — see
`src/compass/adapters/edgar.py`). One 49-second run covered 57 missing
members. Coverage in the development window (2006–2019, member-quarters):

| Theme | Coverage | Note |
|---|---|---|
| ai-chips | 97.7% | |
| cybersecurity | 97.8% | |
| airlines-travel | 82.9% | |
| big-box-retail | 82.1% | |
| cloud-software | 78.8% | |
| energy | 73.9% | |
| healthcare-glp1 | 72.3% | |
| ai-memory-storage | 71.2% | |
| **data-centers-power** | **67.6%** | below 70% — shrink-the-claim applies |
| **banks-payments** | **52.5%** | below 70% — banks report revenue under non-standard XBRL tags (GS 0q, WFC 15q, JPM 26q, MS 29q); the AV loop is filling these |
| **TOTAL** | **76.0%** | ≥ 70% gate: **PASSED** |

XBRL's 2007–2009 mandate start means pre-2009 quarters are structurally
thinner everywhere — recorded, not fudged. EPS estimates/surprise exist only
in Alpha Vantage data (analyst data is not in SEC filings); the 6-hourly AV
loop keeps filling those fields. H2 scoring averages whatever metrics exist
per member.

## Spot checks

10 price rows and 5 fundamentals rows sampled (seed 42, reproducible) and
printed by the coverage command for manual verification against public
sources. Example verified pair: MRVL FQ-end 2007-04-30 reported 2007-07-09 —
a late filing captured correctly; exactly the kind of row `report_date`
provenance exists to get right.
