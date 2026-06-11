# vanta

**STATUS: PAUSED (2026-06-10) — read this before writing any code.**

## Why this project is paused

Vanta was started (2026-06-08) as a data-warehouse foundation for an earnings-options
intelligence app targeting MU's 2026-06-24 earnings — news, filings, estimates, prices for
an "AI Memory" peer universe, with point-in-time provenance.

**The thesis it was built to serve has since been disproven.** The sibling project
[`../prescient`](../prescient) ran an honest, disprove-first backtest over all three retail
earnings-options approaches on 2 years of real data, and **all three failed the survival
gate**:

| Approach | Verdict (2026-06-10) |
|---|---|
| Buy straddle, hold through earnings (the peer read-through thesis) | `survived=False` (+0.1% avg, −100% median) |
| Sell vol defined-risk, hold through | `survived=False` (−83.3% avg, −100% median) |
| Buy 5 days early, sell day before (vol-ramp) | `survived=False` (−7.0% avg, −12.5% median — the ramp exists but the bid/ask spread eats it) |

Full narrative, evidence, and lessons:
`../prescient/docs/program/2026-06-08-prescient-program-review.md` (the program's memory —
read it in full before resuming anything here).

## What this means for the implementation plan

`docs/superpowers/plans/2026-06-08-vanta-data-warehouse-foundation.md` was executed through
the adapter work (scaffold, config, models, schema, store, adapter base, finnhub) on branch
`feat/data-warehouse-foundation`. **Do NOT resume the remaining tasks** (alphavantage/fmp/sec
adapters, orchestrator, live ingestion) without re-reading the prescient program review —
the news/estimates/filings ingestion serves a strategy that no longer has a live hypothesis.

## Candidate futures for this repo (decision pending)

1. **Personal wealth autopilot** (current leading direction — see §9.1 of the prescient
   program review): ~85% Core (cheap index ETFs + trend-following seatbelt, deposit autopilot
   for ~$2k/month contributions), ≤15% Lab (experiments gated by prescient's harness), and a
   behavioral firewall (override pricing, cooling-off rules, drawdown context). Needs a fresh
   brainstorm → spec → plan cycle; the existing Supabase project and store-layer patterns here
   are reusable.
2. **Forward-looking implied-move collector**: a small daily job snapshotting ATM straddles /
   implied moves for a wide liquid universe. Point-in-time IV history cannot be backfilled
   cheaply — every week of delay is permanently lost data. Cheap (~1 day) and compounds in
   value regardless of which strategy direction wins.

These are complementary; (2) can run inside (1)'s Lab.

## Operating rules carried over from prescient

- **Evidence overrides the feeling.** No strategy touches real money without surviving an
  honest backtest, then paper trading.
- Propose-only by default; never commit secrets (`.env`, `.secrets/` are gitignored);
  free data first — paid spend must prove itself.
