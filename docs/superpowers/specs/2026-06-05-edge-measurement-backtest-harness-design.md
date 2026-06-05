# Edge-Measurement Backtest Harness — Design

**Date:** 2026-06-05
**Status:** Design (awaiting review)
**Sub-project:** 1 of 5 in the "single-name earnings-prediction" app rethink

---

## Why this exists (context)

`prescient` is being reconsidered. The owner wants an app that predicts how a stock
will react to its earnings report so they can buy a call (bet up) or put (bet down)
ahead of time, on a small personal account ($10k–25k, propose-only rails).

Before building any prediction engine, signal collectors, or paid data feeds, we build
the tool that tells us whether the idea is even real. The owner explicitly accepted the
governing deal:

> **Evidence overrides feeling.** If a strategy can't beat a coin flip on historical
> data after IV crush and costs, it does not get traded with real money — regardless
> of how strongly it "feels" right or how many online winners were seen.

This document designs that tool. It is the FIRST sub-project; the other four
(universe & calendar, signal collectors, prediction & confidence engine, dashboard)
each get their own spec → plan → build cycle later, and only proceed if this harness
shows the idea survives.

### The whole-app decomposition (for orientation only — not built here)

| # | Sub-project | One-line job |
|---|---|---|
| 1 | **Edge-measurement backtest harness** (THIS doc) | Prove/kill the idea on free historical data |
| 2 | Universe & calendar | Rule-based liquid watchlist + rolling upcoming-earnings feed |
| 3 | Signal collectors | News, revisions, sentiment, peer read-through, implied move |
| 4 | Prediction & confidence engine | Blend signals → direction + predicted move + confidence + selectivity gate |
| 5 | Dashboard rethink | Wide board of upcoming names; the few that clear the gate flagged |

---

## What it is, in one sentence

A machine that replays past earnings and asks: *"If we had traded our strategy back
then, would we have beaten a coin flip after the market's priced-in move and after
option costs?"* — built to **disprove** the strategy, on free data first.

## Governing design commitments

These flow directly from the owner's decisions during brainstorming and are
non-negotiable for this sub-project:

1. **Disprove-first.** Every result is framed as *survived / dead*. A strategy
   "survives" only if it clearly beats dumb baselines (coin flip, always-up) — not
   merely by being profitable (a bull market makes everything look profitable).
2. **Free-data first; paid must prove itself.** Build on data already available
   (Alpaca historical daily bars + options, earnings dates, peer results). Paid data
   is *allowed* but must demonstrably improve the backtest result before becoming a
   dependency. Favor **one-time / evidence purchases** over **recurring subscriptions**
   the edge depends on (recurring "edge" is usually already priced into options).
3. **Grouping is tested, not assumed.** Whether to group companies into themes/peers
   at all is a hypothesis. The harness compares: owner's hand-picked groups vs.
   data-driven (correlation-based) groups vs. no grouping. Evidence decides.
4. **Rule-based universe, locked before testing.** ~20–40 large, liquid, optionable
   US names selected by a mechanical rule (size + liquid options + N years clean
   history), committed up front. NOT "all US companies" (invites overfitting and
   relies on data that doesn't exist for illiquid names) and NOT a gut-tweaked list.
5. **Propose-only / no live anything.** The harness only measures history. It never
   places, sizes, or suggests a live trade. Stays inside the rails in `CLAUDE.md`.

## Relationship to the existing `prescient/backtest` package

The existing package is **welded to the read-through strategy** and measures "did the
underlying move in the expected direction" + "did it beat buy-and-hold." It has **no
concept of the options-implied move**, which is the central metric for an
options-prediction thesis. Therefore this harness is built as a **new,
strategy-agnostic scorer** that reuses the existing historical-data loaders
(`HistoricalPricePoint`, `HistoricalOptionQuote`, Alpaca daily-bars readers) but does
not bend the read-through-specific runner. The old package remains untouched and green.

---

## Inputs and outputs

### Inputs (all free, already in the system)

- **Time window** — e.g. 2024-01-01 → today.
- **Universe** — the rule-based ~20–40 name watchlist (Section: Universe rule).
- **Strategies under trial** — each is a pure function `(point-in-time facts) →
  {action: CALL | PUT | NONE, predicted_move_pct, confidence}`. Initial set:
  1. **Owner thesis** — peers reported well AND their stocks rallied → buy the next
     reporter. (Reaction-aware variant of the original read-through idea.)
  2. **Coin flip** — random CALL/PUT. The bar the thesis must clear.
  3. **Always-up** — always CALL. Catches the "we just rode a bull market" illusion.

### Output — one scorecard per strategy, shown side by side

| Metric | Meaning |
|---|---|
| **Verdict: survived / dead** | Did it clearly beat BOTH baselines? Headline. |
| Directional hit-rate | How often the up/down call was right (table stakes). |
| Beat-the-implied-move rate | How often the realized move landed on the leaned side of the implied move (the real-edge metric). |
| Hypothetical option P&L | If the actual ATM option were bought: P&L after IV crush + cost/spread haircut. |
| Calibration | When "high confidence," was it actually more right? |
| **Sample-size verdict** | Loud N + trust label (e.g. "23 events — too few, treat as a hint"). |

---

## How it scores one earnings event (honest mechanics)

For each past report of each name:

1. **Stand the day before the report.** Use only data knowable then — no peeking.
   Enforced in code (point-in-time loader); a dedicated test fails if the engine ever
   reads a future bar.
2. **Ask the strategy:** CALL, PUT, or NONE.
3. **Record the implied move** — derived from pre-earnings ATM option prices (the
   straddle / IV-implied expected move, ±X%).
4. **Jump to after the report.** Record the realized move from daily closes over the
   evaluation horizon.
5. **Score three ways:** (a) direction correct? (b) realized vs. implied on the leaned
   side? (c) if the actual option were bought, P&L after **IV crush + a realistic
   cost/spread haircut**.

The two anti-lying safeguards: **no peeking** (point-in-time only) and **costs +
IV-crush modeled** (an option bet ignoring those always looks fake-profitable).

## Error handling & sample-size conscience

- **Missing data → skip, never guess.** No usable option quote for a date → event is
  `not_evaluable` and excluded, never filled with a fabricated number. (Matches the
  existing codebase discipline.)
- **Loud sample-size verdict.** Every scorecard states N and a blunt trust label.
  With the owner's data this will frequently say "too few to trust."
- **Survivorship flagged.** Names lacking full history are flagged, not silently
  dropped, so the result isn't quietly biased toward survivors.

## Component boundaries (each small, testable, isolated)

- **Universe rule** — produces the locked watchlist from a mechanical filter.
- **Point-in-time loader** — serves only data knowable as-of a date; refuses the future.
- **Implied-move calculator** — pre-earnings ATM option prices → expected move %.
- **Realized-move calculator** — daily closes → actual move %.
- **Strategy protocol** — the common `(facts) → {action, predicted_move_pct,
  confidence}` interface; thesis + baselines all implement it.
- **Event scorer** — scores one event on the three axes.
- **Option P&L model** — applies IV crush + cost/spread haircut to a hypothetical buy.
- **Scorecard aggregator** — rolls events into the per-strategy scorecard + verdict +
  sample-size label.
- **Grouping evaluators** — hand-groups vs. correlation-derived vs. none, compared.

## Universe rule (locked before testing)

Mechanical filter, committed up front (exact thresholds finalized in the plan):

- Large-cap US equities (market-cap floor), AND
- Liquid listed options (open-interest / volume floor so quotes are real and tradeable),
  AND
- ≥ N years of clean daily + earnings history in free sources.

Yields ~20–40 names. Includes the existing config names where they qualify, but is
**derived from the rule**, not hand-edited to taste. Stored as config so it's explicit
and auditable.

## Testing approach

TDD, small pieces, frequent commits, matching the repo's existing style. Mandatory
tests include:

- **Lookahead-bug catcher** — fails if the engine ever reads data dated after the
  as-of date.
- **IV-crush / cost realism** — a "correct direction but overpaid option" event must be
  capable of scoring a LOSS.
- **Baseline sanity** — coin-flip ≈ 50% directional over a large synthetic sample;
  always-up tracks the underlying drift.
- **Skip-not-guess** — missing quotes produce `not_evaluable`, never a fabricated value.
- **Sample-size labeling** — small N yields the loud low-trust verdict.

## Explicitly out of scope (later sub-projects)

- Any live or paper trading.
- News / sentiment / analyst-revision collectors (sub-project 3).
- The blending prediction engine and selectivity gate (sub-project 4).
- Dashboard changes (sub-project 5).
- Paid data integration (allowed later only if it proves itself here first).

## Success criteria for this sub-project

- The harness runs over the locked universe + time window on free data.
- It produces side-by-side scorecards for thesis vs. coin-flip vs. always-up.
- The implied-move and IV-crush/cost mechanics are present and test-covered.
- The lookahead-bug catcher and skip-not-guess tests pass.
- Whatever the verdict (survived or dead), it is delivered with an honest
  sample-size label — the owner can act on evidence, not feeling.
