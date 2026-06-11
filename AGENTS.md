# Operating rules for any agent or human working in compass

These rules are carried over from the prescient program and are non-negotiable.
They bind every session, every phase, and every future direction of this repo.

## The founding rule

**Evidence overrides the feeling.** No strategy, signal, or screen ships in the app
without surviving the backtest protocol in `docs/specs/2026-06-10-rulebook.md`.
"It feels like it should work" routes to the harness, never to money.

## Hard rules

1. **Propose-only forever.** This system never places, sizes, authorizes, or
   auto-executes a trade. There is no order-placement code in this repo, in any phase.
   The human reads the proposal and clicks (or doesn't) in their own broker.
2. **No-lookahead is sacred.** At any simulated date, code may only use data that was
   knowable on that date: prices through that day, fundamentals as reported by then,
   theme memberships as they existed then (memberships are dated facts). The realized
   future is visible only to the scorer, never to the strategy.
3. **Never commit secrets.** `.env` and any key material are gitignored and never
   pasted into chat, code, fixtures, or docs.
4. **Free data first.** Paid data must prove its value in a backtest before any
   recurring spend. Prefer one-time/evidence purchases over subscriptions.
5. **Develop/validate split is one-shot.** Rules are developed on pre-2020 data.
   The 2020-present validation window is used exactly once per hypothesis. Re-running
   validation after tweaking parameters is overfitting and is forbidden.
6. **No parameter sweeps to rescue a dead strategy.** If a hypothesis fails its kill
   condition, it is recorded as failed. Sweeping parameters until something looks
   positive manufactures overfit, not edge (prescient lesson 9).
7. **Median and worst case, never just the mean.** Every scorecard reports median,
   mean, max drawdown, and sample-size honesty labels (prescient lesson 3).
8. **Costs are modeled pessimistically.** Trading costs and a short-term
   capital-gains tax haircut are charged in every backtest. When in doubt, make the
   cost assumption hurt (prescient lesson 8).
9. **Never `git add -A`.** Add only specific named files.
10. **Update the record.** When a hypothesis verdict lands or direction changes,
    update the rulebook's verdict table and the README status in the same change.

## Permanent non-goals

- No options strategies (three were tested honestly in prescient; all failed).
- No real-time/streaming ingestion; nightly batch only. The app competes at the
  months timescale, not the seconds timescale.
- No auto-trading, no broker write access, ever.
- No intraday signals.

## Tech constraints

- Python 3.11, `uv` as dependency manager and command runner.
- Supabase/Postgres as the durable store; every fact-bearing row carries both its
  real-world timestamp (e.g. `published_at`, `report_date`) and `ingested_at`
  (when we learned it) — point-in-time provenance, the vanta pattern.
- FastAPI with versioned `/v1` routes (Phase 3+). Backend logic only behind the API;
  the front end renders, it never computes.
