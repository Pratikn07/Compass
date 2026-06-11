# compass

A calm, once-a-day investing advisor: it tells you **where industries are moving**
(theme trends), **whether the money is real** (financial reality), and **who in a
strong theme hasn't been paid yet** (laggard radar). It proposes; the human decides.

**Founding rule (inherited from prescient, non-negotiable):**

> *Evidence overrides the feeling.*

No signal in this project earns a place in the app — and no strategy ever touches
real money — without first surviving an honest, disprove-first backtest. The app is
built around what survives, not around what feels right.

## Where this project sits

- [`../prescient`](../prescient) — the referee. A disprove-first backtest harness that
  already killed three retail earnings-options strategies on 2 years of real data for $0.
  Its governance model (propose-only, no-lookahead, honest costs, sample-size honesty)
  is carried into this project wholesale. Read
  `../prescient/docs/program/2026-06-08-prescient-program-review.md` for the full story.
- [`../vanta`](../vanta) — paused. A point-in-time data-warehouse foundation built for a
  thesis that was later disproven. Its model patterns (`ingested_at` provenance,
  normalized adapter records) are reused here in spirit.
- **compass** — the next chapter: stocks and theme baskets at the **months** timescale,
  where a person with a laptop has a fair fight. No options. No streaming. No speed race.

## Current status

**Phase 2 — backtest harness built and calibrated; H1 judged; H2/H3 awaiting data.**

- Rulebook (Phase 0): [`docs/specs/2026-06-10-rulebook.md`](docs/specs/2026-06-10-rulebook.md)
  — verdict table of record in §5.6
- Data foundation (Phase 1): price gate **PASSED** (100%, all 85 tickers,
  2006→present); fundamentals 12/74 members, resuming daily under the Alpha
  Vantage cap ([`docs/phase1-gate-evidence.md`](docs/phase1-gate-evidence.md))
- **Referee calibrated** (Phase 2): Faber 10-month SMA on SPY reproduced —
  9.3% CAGR / −19% maxDD vs 8.0% / −51% buy-and-hold
- **H1 development: partial.** Broad theme-trend claim failed (6/8 ETFs lose
  on after-tax Sharpe); only XLF survived robustly across the sensitivity
  grid. Crash protection (drawdown bar) passed almost everywhere — taxes ate
  the rest
- **H2: SURVIVED — development, sensitivity, AND one-shot validation**
  (spent 2026-06-11 on owner go-ahead). Development: +4.2%/yr top-vs-bottom
  theme spread at the 6-month horizon. Validation 2020→present: direction
  and ordering held, +19.4%/yr (regime-flattered; `too_few` honesty cap).
  The first full survivor in the program — **the Phase 2 → 3 gate is
  passed**
- **H3 development: FAILED** — 268 laggard trades, base rate 50.4% (coin
  flip), dead at all 18 sensitivity grid points. The laggard radar ships in
  no app
- Full record: [`docs/phase2-results.md`](docs/phase2-results.md)
- H1 validation remains one-shot and unspent (XLF-only claim; owner may
  spend, hold, or pre-register an IRA variant)

Commands: `compass.ingest` (backfill / crosscheck / coverage) and
`compass.backtest.runner` (calibrate / develop / sweep / validate), both via
`uv run python -m ...`. Prices come from the Yahoo chart API (Stooq is
bot-walled; deviation recorded in the Phase 1 gate evidence).

## The phases (from the agreed plan)

| Phase | What | Gate to pass |
|---|---|---|
| 0 | Rulebook spec (this) | Rules specific enough that two people would code the same test |
| 1 | Data foundation (prices, fundamentals, filings, dated themes) | Clean, dated, spot-checked data |
| 2 | Backtest all three hypotheses | At least one `survived = true` |
| 3 | FastAPI backend (`/v1`), nightly jobs | A month of clean runs |
| 4 | Front end (Today / Themes board / Laggard radar / Journal) | Owner trusts and uses it |
| 5 | Theme birth detection | Manual theme list becomes the bottleneck |
| 6 | Operate, re-verify quarterly | Ongoing |

Phases 3-5 are built **only** for hypotheses that survive Phase 2. "All three fail" is a
legitimate, documented end state that costs ~$0 — that is the system working.

## Stack (pinned in the rulebook)

Python 3.11 - `uv` - Supabase/Postgres - FastAPI with versioned `/v1` routes (Phase 3) -
nightly batch jobs only. Deliberately never built: streaming/real-time anything,
options anything, auto-trading anything.
