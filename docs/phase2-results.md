# Phase 2 results — running record

**Updated:** 2026-06-10. Verdict table of record: rulebook §5.6.

## Referee calibration — PASSED

The harness reproduced Faber (2007) before judging anything (rulebook §5.1):
10-month SMA timing on SPY, 1993–2012, pre-tax:

| | CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Timing | 9.33% | 0.89 | −19.0% |
| Buy-and-hold | 8.02% | 0.58 | −50.8% |

Similar CAGR, roughly one-third the drawdown — the published signature.
Acceptance bars (CAGR ±1.5pts, maxDD ≤60% of B&H): both passed.

## H1 theme trend — development verdict: PARTIAL (broad claim failed)

SMA(200), monthly evaluation, 2006–2019, after costs AND the pinned tax
haircut, vs each instrument's own buy-and-hold:

| Instrument | Timing CAGR | B&H CAGR | Timing maxDD | B&H maxDD | Survived |
|---|---|---|---|---|---|
| SMH | 3.4% | 9.9% | −29% | −57% | no |
| IGV | 5.7% | 12.2% | −28% | −46% | no |
| CIBR | 9.2% | 13.7% | −20% | −18% | no |
| XLV | 6.1% | 9.3% | −25% | −36% | no |
| JETS | −8.2% | 5.6% | −42% | −17% | no |
| **XLF** | **6.8%** | **2.6%** | **−23%** | **−79%** | **yes** |
| **XLE** | **3.3%** | **2.9%** | **−30%** | **−53%** | **yes** |
| XLY | 9.2% | 10.2% | −24% | −55% | no |
| ai-memory-storage* | 8.6% | 8.6% | −33% | −77% | yes* |
| data-centers-power* | 3.5% | 10.5% | −40% | −47% | no |

*hindsight-curated baskets: may strengthen but never solely produce a verdict
(rulebook §4).

**Sensitivity sweep (§5.5):** XLF survives at every grid point (N=150–250,
monthly and weekly) — robust. XLE fails at N≤175 — an effect that exists only
at some parameter points is noise: **killed**. Net development survivor:
**XLF only**.

**The honest reading:** the seatbelt does exactly what Faber promised on
*drawdowns* (bar 2 passed on 8/10 instruments — crash protection is real),
but after the pinned 35% short-term tax on every exit, timing's
return/Sharpe beat buy-and-hold only where buy-and-hold was demolished
in-window (financials −79%, energy −53%). On themes that mostly went up,
taxes plus whipsaws ate the edge. The broad H1 claim — "trend-time every
theme" — did not survive development. A narrow claim ("trend timing adds
value on crash-prone themes / in tax-sheltered accounts") is a NEW
hypothesis that would need its own pre-registered spec, not a re-run.

**Validation:** NOT run. One-shot, awaiting owner go-ahead (rulebook §5.3).

## H2 financial reality — development verdict: SURVIVED (at the 6-month horizon)

Gate lifted 2026-06-11 at 76.0% member-quarter coverage after the EDGAR
companyfacts source was added by owner decision (banks-payments 52% and
data-centers-power 68% remain under 70% — shrink-the-claim noted on their
contribution; the AV loop keeps improving them).

Quarterly theme rankings by fundamentals (rev growth, margin delta, surprise
z-scores), forward basket returns after costs, 2006–2019:

| Horizon | Top | Middle | Bottom | Spread (ann.) | Monotonic | Survived |
|---|---|---|---|---|---|---|
| 126d | 11.5% | 9.9% | 9.5% | **+4.2%/yr** | yes | **yes** |
| 63d | 6.3% | 4.5% | 5.3% | +4.0%/yr | **no** (middle < bottom) | no |

Sensitivity: 3 of 4 grid cells pass (126d median, 126d mean, 63d mean); only
63d-median breaks monotonicity. The effect exists across the grid — not a
single-point artifact. Sample: 41–42 quarters (`suggestive`, honesty cap).
**The honest reading:** themes with real, accelerating fundamentals beat
hype themes over the *next six months* by ~4 points a year — a ranking edge,
not a get-rich signal, and it must still pass one-shot validation.

## H3 laggard radar — development verdict: FAILED (cleanly)

The "MU ran, so buy SanDisk" idea, tested honestly: 268 trades (`moderate`
sample), mean excess vs just holding the theme basket: **−0.19%**, base rate
50.4%, 95% CI [44%, 56%] — indistinguishable from a coin flip. The
sensitivity grid is unambiguous: **dead at all 18 parameter combinations**
(lookback 60/90/120 × gap 20/25/30pts × hold 63/126d).

The market is not slow at the months timescale either: laggards lag for a
reason about exactly as often as they catch up. The fundamentals-comparability
filter did not separate the two. H3 is recorded as FAILED and ships in no app.

## Reproduction

```bash
uv run python -m compass.backtest.runner calibrate
uv run python -m compass.backtest.runner develop --hypothesis h1
uv run python -m compass.backtest.runner sweep --hypothesis h1
# after fundamentals complete:
uv run python -m compass.backtest.runner develop --hypothesis h2
uv run python -m compass.backtest.runner develop --hypothesis h3
# one-shot, owner go-ahead only:
uv run python -m compass.backtest.runner validate --hypothesis h1 --i-understand-one-shot
```

Raw run artifacts: `docs/results/*.json`. Known approximation on record:
H3's $2B market-cap floor is proxied by the $10M median-dollar-volume floor
(free data has no point-in-time market cap).
