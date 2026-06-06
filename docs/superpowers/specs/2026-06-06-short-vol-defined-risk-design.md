# Short-Vol Defined-Risk Strategy — Design

**Date:** 2026-06-06
**Status:** Design (awaiting review)
**Sub-project:** A new strategy + P&L model on the existing edge harness, testing whether
the volatility risk premium is harvestable by a small account via a defined-risk,
unhedged, sell-and-hold short straddle around earnings.

---

## Why this exists

The edge harness disproved the peer read-through thesis (buying straddles): 30%
directional accuracy, IV crush eating the rare correct calls, outlier-driven returns,
`survived=False`. The per-event diagnostic surfaced a real, documented pattern: the
stock moved LESS than the options-implied move in ~70% of events (28/40). That points
to SELLING volatility rather than buying it.

Internet research (2026-06-06) confirmed: harvesting the volatility risk premium is a
recognized institutional strategy (volatility arbitrage; LTCM ran it). BUT funds capture
it via **continuous delta-hedging of a diversified portfolio** — "profit is extracted
through the continuous re-hedging required to keep the portfolio delta-neutral" — and
even diversified short-vol blows up in correlated black-swan events (e.g. Feb 2018
"Volmageddon", where short-vol products lost ~96% in a day).

A small account cannot delta-hedge continuously or diversify across hundreds of names.
So this sub-project tests the **only version a retail account could actually run**: a
**defined-risk (capped-loss), unhedged, sell-and-hold** short straddle. Defined risk is
the small-account substitute for the funds' hedging+diversification survival mechanism.

## What this is NOT

- NOT the institutional delta-hedged version (operationally impossible for a small
  account; we do not model continuous hedging).
- NOT a recommendation to trade. Propose-only research tooling; nothing places, sizes,
  authorizes, or recommends a trade.
- NOT naked short straddle (unbounded risk). Loss is always capped.

## Critical interpretation rule (honesty gap)

Because we do NOT model delta-hedging, a result must be read as a verdict on **the
retail, unhedged, defined-risk, sell-and-hold version** — NOT on whether the volatility
risk premium exists at all. A "does not survive" outcome means "this version a small
account could run does not beat the baselines after honest costs," NOT "the premium
isn't real." The premium may be real yet only capturable with hedging/diversification
machinery the owner does not have.

---

## The honest P&L model (the core of this design)

New function `simulate_capped_short_straddle_pnl(...)`, beside the existing buy-side
`simulate_option_pnl` (which is NOT changed). For one event:

- **Credit collected** = `straddle_price` = ATM call close + ATM put close (the premium
  received for selling; we already fetch this).
- **Realized payout owed** = the in-the-money value the short straddle owes at the
  evaluation point, based on the realized underlying move in dollars from the as-of
  close: `payout = |post_close - underlying_price|` (a sold straddle owes the absolute
  move beyond the strike; ATM strike ~ underlying, so payout ~= |realized $ move|).
- **Wing cost (the honesty haircut)** = estimated cost of the protective long wings that
  CAP the loss at width `W`. It scales INVERSELY with `W`: a tighter cap (smaller W,
  safer) costs MORE credit; a wider cap costs LESS. Modeled as
  `wing_cost = credit * wing_cost_frac(W)` where `wing_cost_frac` decreases as W grows
  (exact form fixed in the plan; e.g. proportional to `straddle_price / W` clamped to
  [0,1]). This enforces "you cannot collect full premium AND get cheap protection."
- **Net P&L** = `credit - wing_cost - payout`, then FLOORED at `-W` (defined risk: you
  can never lose more than the wing width). Minus the same bid/ask `cost_haircut_pct`.
- **Capital at risk** = `W`. **Return %** is measured on `W` (not on the small premium),
  so the numbers are comparable to a real defined-risk trade and not inflated.
- Returns None on invalid inputs (non-positive credit/W). If `wing_cost >= credit` the
  trade is unprofitable by construction and recorded honestly (a real signal that the
  trade isn't worth doing on that name) — NOT skipped.

`W` is a parameter (capital at risk per trade), defaulted in the plan to a small,
account-appropriate value; it can be swept later.

## Components (all additive; nothing frozen is rewritten)

1. **`option_pnl.py`** — add `simulate_capped_short_straddle_pnl(...)`. Pure,
   hand-computed unit tests.
2. **`models.py`** — extend `Prediction` with `sell_straddle: bool = False` (defaults
   false → existing strategies untouched). Extend `EventScore` with
   `stayed_within_implied: bool | None = None`.
3. **`strategy.py`** — add `ShortVolStrategy`: emits `direction=NONE,
   sell_straddle=True, confidence` (a fixed/derived confidence; it always wants to sell
   when a straddle exists). It is non-directional by design.
4. **`scorer.py`** — add a sell-vol branch: when `prediction.sell_straddle` and both ATM
   legs exist, compute the implied move, the realized move, set `stayed_within_implied`
   = (|realized| < implied), and set `option_pnl` from
   `simulate_capped_short_straddle_pnl`. Directional predictions still score exactly as
   today (no regression). `direction_correct`/`beat_implied` stay None for a pure
   sell-vol (non-directional) prediction.
5. **`runner.py`** — `ShortVolStrategy` is added to the strategy list. The survival
   metric must be unambiguous for a non-directional strategy. The existing gate compares
   `beat_implied_rate` to the baselines; for a pure sell-vol prediction `beat_implied` is
   None, so `beat_implied_rate` would be None. **Decision (locked):** generalize the
   survival rule so that, for ANY strategy, survival requires positive
   `average_option_return_pct` (on capital-at-risk) AND not `TOO_FEW` AND a return margin
   over the best baseline's average return — the comparison axis becomes **average
   return** (which every strategy has), with beat-implied kept as a reported diagnostic.
   This keeps the directional strategies' bar AT LEAST as strict (they must still make
   money AND beat baselines on return), while making the gate well-defined for sell-vol.
   A regression test asserts the prior read-through result still does NOT survive under
   the generalized rule (the change must not make a previously-failing strategy pass).
6. **`run_edge_backtest.py`** — add `ShortVolStrategy()` to the strategy list so the
   live scorecard includes it alongside the existing three.

## What stays exactly as-is

Data assembly, historical-options reader, implied/realized move calcs, the no-lookahead
discipline, the buy-side `simulate_option_pnl`, the three existing strategies, and the
baselines.

## Error handling (skip-not-guess)

- No straddle for an event → `not_evaluable` (same as today).
- `simulate_capped_short_straddle_pnl` returns None on invalid inputs.
- `wing_cost >= credit` → trade recorded as unprofitable-by-construction, not skipped.
- Loss always floored at `-W` (defined risk holds even on a 20%+ move).

## Testing (TDD, hand-computed, no live calls)

- `simulate_capped_short_straddle_pnl`:
  - small move (inside) → keep credit minus wings → modest WIN;
  - big move (breaks cap) → loss floored at exactly `-W` (proves defined risk);
  - tighter `W` → larger wing haircut → smaller net credit (proves the honesty
    trade-off);
  - return measured on `W`, not premium;
  - `wing_cost >= credit` → non-positive net, recorded not skipped.
- `ShortVolStrategy`: emits `direction=NONE, sell_straddle=True`.
- `Prediction`/`EventScore`: new fields default safely; existing construction unaffected.
- `scorer`: sell-vol branch sets `stayed_within_implied` + short `option_pnl`; a
  directional strategy still scores the old way (explicit no-regression test).
- `runner`: ShortVol included; survival applies; a negative-return short-vol result does
  NOT survive.

## What the result will tell you (expectations set honestly)

- **If ShortVol survives** (beats baselines, positive return on capital-at-risk after
  wings + capped tails, decent sample): genuinely interesting — the retail defined-risk
  version may be viable. Next step would be paper-trading a full season before any real
  money. Still subject to the black-swan caveat (one Volmageddon-style correlated move).
- **If it does not survive** (honest prior, given the research): you will have proven
  with your own data that even the smart, defined-risk, retail version of earnings
  vol-selling does not beat a coin flip after honest costs — closing the loop that
  earnings options are a poor game for a small account, for $0.

Either outcome is a real, valuable answer. Interpret per the "Critical interpretation
rule" above: this tests the retail unhedged version, not the existence of the premium.

## File layout

```
src/prescient/edge/option_pnl.py   # + simulate_capped_short_straddle_pnl
src/prescient/edge/models.py        # + Prediction.sell_straddle, EventScore.stayed_within_implied
src/prescient/edge/strategy.py      # + ShortVolStrategy
src/prescient/edge/scorer.py        # + sell-vol scoring branch
src/prescient/edge/runner.py        # (only if the gate needs a None-direction accommodation)
scripts/run_edge_backtest.py        # + ShortVolStrategy in the strategy list
tests/test_edge_option_pnl.py       # + capped-short tests
tests/test_edge_strategies.py       # + ShortVolStrategy test
tests/test_edge_scorer.py           # + sell-vol branch + no-regression test
tests/test_edge_runner.py           # + ShortVol survival test
```

## Success criteria

- `simulate_capped_short_straddle_pnl` passes all hand-computed tests, especially the
  `-W` floor and the inverse wing-cost trade-off.
- The sell-vol scorer branch produces correct short-trade P&L and `stayed_within_implied`;
  directional strategies show NO regression.
- `run_edge_backtest.py --limit N` prints a scorecard row for `short_vol` alongside the
  existing three, with return measured on capital-at-risk and an honest survival verdict.
- Whatever the verdict, it is delivered with the sample-size label and read per the
  retail-version interpretation rule.

## Explicitly deferred

- Delta-hedged (institutional) version — operationally impossible for the account; not
  modeled.
- Full 4-strike iron condor with real wing prices — the capped-short approximation is
  the chosen first test.
- `W` parameter sweep — single default first; sweep only if the strategy shows promise.
- Forward paper-trading — only if it survives.
