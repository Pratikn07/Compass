# Pre-Earnings Vol-Ramp Strategy — Design

**Date:** 2026-06-07
**Status:** Implemented 2026-06-10 (plan: `docs/superpowers/plans/2026-06-10-pre-earnings-vol-ramp.md`); spec synced to the strike-locked context fields. Two deviations from the original draft, both correctness-driven:
1. **Strike-locked exit quotes.** The original §4 read the exit value from the context's existing `atm_call`/`atm_put`, but those are ATM **at exit** — after ~5 days of drift they can be a different contract than the one bought at entry, violating this spec's own strike-consistency rule (and overwriting them would change the implied move for every other strategy). The implementation carries FOUR dedicated fields on `EventContext` instead: `vol_ramp_entry_call/put` (stamped `entry_as_of_date`) and `vol_ramp_exit_call/put` (same strike+expiration, stamped `as_of_date`). `atm_call`/`atm_put` are untouched.
2. **No SDK reader changes.** The existing `historical_option_reader` lists contracts by expiration window independent of the as-of date, so `get_historical_vol_ramp_straddle` simply calls it twice (entry day, exit day) — `live_data/alpaca_readers.py` was not modified.
**Sub-project:** A new direction-free strategy + P&L model on the existing edge harness,
testing whether a small account can profit by **buying the ATM straddle ~1 week before
earnings and selling it the day before the report** — capturing the rise in implied
volatility into the event while never holding through it (so it never eats IV crush and
never has to predict direction).

---

## Why this exists

The harness has now disproved BOTH directions of the *through-earnings* options trade for
a small account, for $0:

- **Buying** the straddle and holding through the report: ~33% directional accuracy,
  returns destroyed by IV crush, outlier-driven, `survived=False`.
- **Selling** defined-risk vol through the report: −79.5% average, −100% median, killed
  by fat tails, `survived=False`.

Both tests share one trait: they **entered near the report and held through the event**.
That is exactly where IV crush lives and where direction has to be guessed.

The user's original instinct was "enter ~7 days before so volatility is in our favor."
That sentence describes a *different, untested* phenomenon: implied volatility **rises**
as earnings approach (the market bids up options ahead of a known binary event). A trade
that **buys cheap vol early and exits before the announcement** harvests that ramp and:

1. **Never eats IV crush** — it is closed before the event fires.
2. **Never predicts direction** — it is a pure long-volatility bet (own both legs).

This is genuinely new information. We have never tested entering early and exiting before
the event.

## What this is NOT

- NOT a directional bet. We do not predict up/down. We own the ATM call AND put.
- NOT a through-earnings hold. We **exit the trading day before** the report. We never
  touch any post-event price — by construction this test cannot eat IV crush.
- NOT a recommendation to trade. Propose-only research tooling; nothing places, sizes,
  authorizes, or recommends a trade.
- NOT a claim the edge is free. Theta (time decay) bleeds the position every day it is
  held, and we cross the bid/ask spread **twice** (in and out). The ramp must beat both.

## The honest prior

This is the most well-known "free lunch" in earnings options, which means market makers
may have already priced the vol ramp into the entry premium. If so, the double spread +
theta eat it and it will not survive. That is a perfectly good, free outcome: we will
have measured it on the user's own data rather than assumed it.

---

## The trade, precisely

For one earnings event on ticker T reporting on date `earnings_date`:

- **Entry** on `entry_as_of_date` = the trading day closest to `entry_lead_trading_days`
  (default **5 trading days ≈ one calendar week**) before `earnings_date`. Choose the ATM
  straddle whose **expiration falls AFTER `earnings_date`** (so the option still has the
  earnings event embedded and is still building vol), within the existing
  `max_expiration_days` window (14 days past earnings). The ATM strike is the listed
  strike nearest the entry-day underlying close.
- **Exit** on `as_of_date` = the last trading day strictly before `earnings_date` (the
  same as-of the harness already computes — its existing `atm_call`/`atm_put`). We sell
  the **same contract** we bought: same strike, same expiration, priced at its exit-day
  close.
- We **never hold through the report**. No post-event price is read for this strategy.

**Strike consistency (important honesty point):** we hold ONE position. The strike is
chosen ATM **at entry** and that SAME strike+expiration is priced at exit. We do NOT
re-pick ATM at exit (that would model a position we never held). Over ~5 trading days the
underlying may drift, so the exit straddle may no longer be exactly ATM — that is correct
and realistic.

---

## The honest P&L model (the core of this design)

New function `simulate_vol_ramp_pnl(...)`, beside the existing `simulate_option_pnl` and
`simulate_capped_short_straddle_pnl` (neither is changed). For one event:

- **Entry premium paid** = `entry_call_close + entry_put_close` (cost to buy the straddle
  at entry).
- **Exit value received** = `exit_call_close + exit_put_close` (proceeds from selling the
  same straddle the day before earnings).
- **Double bid/ask spread (the honesty haircut):** history has only closes, no quotes, so
  we model crossing the spread on the way IN and again on the way OUT. You buy at
  `entry_premium * (1 + cost_haircut_pct)` and sell at `exit_value * (1 - cost_haircut_pct)`.
  This deliberately pays the spread twice — ATM weekly straddle spreads are wide, so a
  pessimistic bias is the correct one for a thin, well-known edge.
- **Net P&L** = `exit_value * (1 - cost_haircut_pct) - entry_premium * (1 + cost_haircut_pct)`.
- **Return %** = `net_pnl / entry_premium * 100`, floored at **−100%** (you cannot lose
  more than the premium paid). Theta is captured implicitly: if vol did not ramp enough,
  the exit value will have decayed below entry and the return is simply negative.
- Returns **None** on invalid inputs (non-positive entry premium or exit value).

`cost_haircut_pct` reuses the existing `_COST_HAIRCUT_PCT = 0.05` (5% per side ⇒ ~10%
round-trip drag), so the cost assumption is consistent with the rest of the harness.

`OptionPnl` is reused unchanged: `entry_premium` = premium paid, `exit_value` = proceeds,
`cost_haircut` = the total modeled spread cost, `net_pnl`, `return_pct`.

---

## Components (all additive; nothing frozen is rewritten)

1. **`option_pnl.py`** — add `simulate_vol_ramp_pnl(*, entry_premium, exit_value,
   cost_haircut_pct) -> OptionPnl | None`. Pure, hand-computed unit tests.
2. **`models.py`**:
   - `Prediction` — add `buy_vol_ramp: bool = False` (defaults false → existing strategies
     untouched).
   - `EventContext` — add `entry_as_of_date: date | None = None` plus FOUR strike-locked
     quote fields: `vol_ramp_entry_call/put` (stamped `entry_as_of_date`) and
     `vol_ramp_exit_call/put` (same strike+expiration, stamped `as_of_date`). All default
     None → existing construction unaffected; the existing `atm_call`/`atm_put` remain the
     exit-side ATM quotes used for the implied move and the through-earnings strategies.
3. **`strategy.py`** — add `VolRampStrategy`: emits `direction=NONE, buy_vol_ramp=True,
   confidence=0.5`. Non-directional by design. It also declares a class attribute
   `exits_before_event = True` (existing strategies implicitly False) so the runner can
   apply the correct survival bar (see §5).
4. **`scorer.py`** — add a vol-ramp branch: when `prediction.buy_vol_ramp` and all four
   `vol_ramp_*` legs exist, compute
   `entry_premium = vol_ramp_entry_call.bid + vol_ramp_entry_put.bid`
   (history stamps bid == ask == close, so either field is the close) and
   `exit_value = vol_ramp_exit_call.bid + vol_ramp_exit_put.bid` — the SAME contracts,
   priced the day before earnings — then set `option_pnl = simulate_vol_ramp_pnl(...)`.
   Missing any leg → `not_evaluable_reason="missing_vol_ramp_straddle"`. `direction_correct`,
   `beat_implied`, and `stayed_within_implied` stay **None** (non-directional, non-event).
   `implied_move_pct`/`realized_move_pct` are still reported as diagnostics from the
   exit-ATM quotes but are NOT used in this strategy's P&L. The directional and sell-vol
   branches are untouched (explicit no-regression test).
5. **`runner.py`** — generalize the survival bar by strategy type, WITHOUT weakening the
   existing gate:
   - **Through-earnings strategies** (`exits_before_event = False`, i.e. every existing
     strategy): survival rule is **exactly as today** — positive `average_option_return_pct`
     AND not `TOO_FEW` AND beats the best baseline's average return by the existing margin.
     A regression test asserts the prior directional/sell-vol survival verdicts are
     unchanged.
   - **Exit-before-event strategies** (`exits_before_event = True`, i.e. `VolRampStrategy`):
     the economically correct alternative is **doing nothing** (the trade takes no event
     risk and no directional risk). Survival requires positive `average_option_return_pct`
     by the existing margin **over zero** (the do-nothing bar) AND not `TOO_FEW`. The drift-
     inflated coin-flip / always-up baselines are STILL computed and reported as diagnostic
     notes, but they are NOT the comparator for this strategy — they hold through earnings
     and rode bull-market drift, so they are not apples-to-apples for a pre-event timing
     trade. This is documented in a scorecard note so the verdict is read correctly.
   - **Why this is not weakening:** the do-nothing bar applies ONLY to strategies that take
     no event/direction risk; every existing strategy keeps the strict beat-the-baselines
     bar. The new bar is additive and clearly scoped, not a relaxation of the old one.
6. **Data assembly (`prescient.edge.data`)** — fetch the strike-locked entry+exit straddle:
   - **`alpaca_market.py`** — add `get_historical_vol_ramp_straddle(*, underlying_symbol,
     entry_as_of_date, exit_as_of_date, entry_underlying_price, earnings_date,
     max_expiration_date) -> list[OptionQuote]`. It calls the EXISTING
     `historical_option_reader` twice (once per as-of date), picks the **earliest in-window
     expiration** then the ATM strike using `entry_underlying_price` (nearest-strike,
     lower-strike-tie rule), and returns FOUR quotes for that SAME strike+expiration:
     entry call, entry put (stamped `entry_as_of_date`), exit call, exit put (stamped
     `exit_as_of_date`), each priced at its bar close. Returns `[]` on any missing piece
     (no contracts, missing a leg, missing either close) — skip, never guess.
   - **`live_data/alpaca_readers.py`** — **unchanged.** The existing reader lists contracts
     by expiration window independent of the as-of date, so two calls cover entry and exit.
   - **`option_loader.py`** — add `load_vol_ramp_straddles_for_events(...)` that, per event,
     derives the entry day from the bar history (the trading day `entry_lead_trading_days`
     bars before the exit as-of day — never a calendar subtraction), looks up the entry-day
     underlying close, calls `get_historical_vol_ramp_straddle`, and returns the four quotes
     keyed by `(ticker, report_date)`. Skips an event when the as-of price, entry-day close,
     bar history depth, or any straddle leg is missing.
   - **`assembler.py`** — accepts `vol_ramp_quotes` (default None → unchanged behavior) and
     threads the four quotes into `EventContext.entry_as_of_date` + the `vol_ramp_*` fields
     (the existing exit-ATM quotes stay as `atm_call`/`atm_put`). No-lookahead holds: entry
     quotes use only entry-day data, exit quotes use only day-before-earnings data, and the
     vol-ramp P&L reads NO post-event price at all.
7. **`run_edge_backtest.py`** — wire the entry-straddle fetch and add `VolRampStrategy()` to
   the strategy list so the live scorecard includes a `vol_ramp` row alongside the existing
   strategies.

## What stays exactly as-is

The buy-side `simulate_option_pnl`, the capped-short `simulate_capped_short_straddle_pnl`,
implied/realized move calcs, the existing strategies and baselines, the existing
`get_historical_atm_straddle` (exit-side), and the no-lookahead discipline.

## Error handling (skip-not-guess)

- No entry straddle, no exit straddle, or a missing leg/close → event `not_evaluable` for
  the vol-ramp strategy (same skip semantics as today; other strategies still score).
- `simulate_vol_ramp_pnl` returns None on non-positive entry premium or exit value.
- Loss floored at −100% of premium (you cannot lose more than you paid).
- No entry trading day available within range (e.g. ticker history too short) → skip event.

## Testing (TDD, hand-computed, no live calls)

- `simulate_vol_ramp_pnl`:
  - vol ramped (exit > entry) after double spread → positive return;
  - vol flat/decayed (exit ≤ entry) → negative return, never worse than −100%;
  - the double-spread haircut is applied to BOTH legs (hand-computed exact number);
  - return measured on entry premium;
  - non-positive entry premium or exit value → None.
- `VolRampStrategy`: emits `direction=NONE, buy_vol_ramp=True`; `exits_before_event` True.
- `Prediction`/`EventContext`: new fields default safely; existing construction unaffected.
- `scorer`: vol-ramp branch sets `option_pnl` from entry+exit straddles with
  `direction_correct`/`beat_implied`/`stayed_within_implied` = None; directional and
  sell-vol branches show NO regression (explicit test).
- `runner`: `VolRampStrategy` uses the do-nothing (zero) bar; a negative-return vol-ramp
  result does NOT survive; an explicit regression test asserts the prior through-earnings
  survival verdicts are unchanged under the generalized gate.
- `get_historical_vol_ramp_straddle`: picks ATM at entry, prices the SAME strike at exit,
  returns four correctly-stamped quotes; `[]` when a leg/close/contract is missing.
- `load_vol_ramp_straddles_for_events`: computes entry_as_of from bars, threads entry-day
  price, skips events with no entry price or missing straddle.

## What the result will tell you (expectations set honestly)

- **If vol_ramp survives** (positive average return on premium after double spread + theta,
  beats the do-nothing bar by the margin, decent sample): genuinely interesting — the
  pre-earnings vol ramp may be harvestable by a small account without event or direction
  risk. Next step would be paper-trading a full season before any real money, and a check
  on drawdown / worst-case (the ramp can fail to materialize in calm markets).
- **If it does not survive** (the honest prior, given market makers likely price the ramp):
  you will have proven with your own data that even the timing-based, direction-free,
  IV-crush-avoiding version does not beat doing nothing after honest costs — closing the
  loop that earnings options are a poor game for a small account, for $0, across ALL three
  approaches (buy-through, sell-through, buy-early-sell-before).

Either outcome is a real, valuable answer.

## File layout

```
src/prescient/edge/option_pnl.py                 # + simulate_vol_ramp_pnl
src/prescient/edge/models.py                      # + Prediction.buy_vol_ramp; EventContext entry_* fields
src/prescient/edge/strategy.py                    # + VolRampStrategy (exits_before_event=True)
src/prescient/edge/scorer.py                      # + vol-ramp scoring branch
src/prescient/edge/runner.py                      # + exits_before_event do-nothing survival bar
src/prescient/edge/data/option_loader.py          # + load_vol_ramp_straddles_for_events
src/prescient/edge/data/assembler.py              # thread entry_* quotes into EventContext
src/prescient/data/alpaca_market.py               # + get_historical_vol_ramp_straddle
src/prescient/live_data/alpaca_readers.py          # entry/exit strike-locked bar reads
scripts/run_edge_backtest.py                      # wire entry fetch + VolRampStrategy
tests/test_edge_option_pnl.py                      # + vol-ramp P&L tests
tests/test_edge_strategies.py                      # + VolRampStrategy test
tests/test_edge_scorer.py                          # + vol-ramp branch + no-regression test
tests/test_edge_runner.py                          # + do-nothing survival + regression test
tests/test_edge_data_option_loader.py              # + vol-ramp loader tests
tests/test_alpaca_market.py                        # + get_historical_vol_ramp_straddle tests
```

## Success criteria

- `simulate_vol_ramp_pnl` passes all hand-computed tests, especially the double-spread
  haircut and the −100% floor.
- The vol-ramp scorer branch produces correct P&L from entry+exit straddles; directional
  and sell-vol strategies show NO regression.
- `run_edge_backtest.py --limit N` prints a `vol_ramp` row with return measured on entry
  premium and an honest do-nothing survival verdict + diagnostic baseline note.
- Whatever the verdict, it is delivered with the sample-size label.

## Explicitly deferred

- `entry_lead_trading_days` sweep (5 vs 3 vs 10) — single default first; sweep only if it
  shows promise.
- Modeling theta explicitly — it is captured implicitly via the exit-vs-entry close
  difference; no separate theta model needed.
- Re-picking ATM at exit / rolling strikes — we hold one fixed strike; out of scope.
- Forward paper-trading — only if it survives.
- A disk cache for the entry straddles (flagged, deferred like the exit-straddle cache).
