# Pre-Earnings Vol-Ramp Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the direction-free pre-earnings vol-ramp strategy to the edge harness: BUY the ATM straddle ~5 trading days before earnings, SELL the same contracts the day before the report, never holding through. This tests whether the pre-earnings IV ramp is harvestable by a small account after theta and a double bid/ask spread — the third and final earnings-options approach (buy-through and sell-through both `survived=False`).

**Architecture:** Additive only — a new pure `simulate_vol_ramp_pnl` beside the two existing P&L models, a `buy_vol_ramp` flag on `Prediction`, four strike-locked vol-ramp quote fields + `entry_as_of_date` on `EventContext`, a `VolRampStrategy` with `exits_before_event = True`, a vol-ramp branch in the scorer, a runner survival bar generalized by strategy type (do-nothing bar for exit-before-event strategies; the existing bar is untouched for everything else), a vol-ramp straddle method on the Alpaca adapter that REUSES the existing `historical_option_reader` (called once at entry, once at exit — **no SDK reader changes needed**), a loader, assembler threading, and live-script wiring. Nothing frozen is rewritten; existing strategies must show no regression.

**Tech Stack:** Python >=3.11, Pydantic v2 (frozen, extra="forbid"), pytest, ruff (line-length 100), uv. Branch: continue on `feat/edge-backtest-harness` (same as short-vol).

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-07-pre-earnings-vol-ramp-design.md` (read it first, including "The honest prior" and the strike-consistency section).

## Spec correction (resolved during planning — implement THIS, then sync the spec)

The spec contradicts itself: §4 (scorer) says `exit_value = atm_call.bid + atm_put.bid` (the context's existing exit-side quotes), but those are picked **ATM at exit** by `loader._atm_quote`. The spec's own strike-consistency rule (§"The trade, precisely") demands we sell **the SAME strike+expiration we bought at entry**. Over ~5 trading days the underlying drifts, so exit-ATM can be a different contract — pricing it would model a position we never held, and overwriting `atm_call`/`atm_put` with strike-locked quotes would silently change the implied move used by every OTHER strategy (regression).

**Resolution (additive, honest):** `EventContext` gains FOUR dedicated quote fields — `vol_ramp_entry_call`, `vol_ramp_entry_put` (stamped `entry_as_of_date`) and `vol_ramp_exit_call`, `vol_ramp_exit_put` (same strike+expiration, stamped `as_of_date`) — plus `entry_as_of_date`. The existing `atm_call`/`atm_put` stay exactly as they are (exit-ATM, used for implied move and the through-earnings strategies). The vol-ramp scorer branch reads ONLY the four `vol_ramp_*` fields. After implementation, update the spec's §2/§4/§6 to match (Task 10).

## Verified facts about the existing code (read 2026-06-10)

- `Prediction` (`src/prescient/edge/models.py`): frozen, has `sell_straddle: bool = False`. Add `buy_vol_ramp: bool = False` beside it.
- `EventContext` (same file): frozen; fields `ticker, earnings_date, as_of_date, underlying_price, atm_call, atm_put, peer_eps_surprises, peer_stock_reactions, realized_move`. Docstring says as-of fields only for strategies; realized fields are scorer ground truth.
- `OptionPnl` (same file): frozen, `entry_premium, exit_value, cost_haircut, net_pnl, return_pct`.
- `option_pnl.py`: `simulate_option_pnl` (buy-through) and `simulate_capped_short_straddle_pnl` (sell-through). Leave both untouched.
- `scorer.py`: `_COST_HAIRCUT_PCT = 0.05`, `_DEFAULT_RISK_WIDTH_W = 5.0`. `score_event` early-returns `not_evaluable` on missing realized move, then on missing implied move. The sell-vol branch keys off `prediction.sell_straddle`; the buy branch off direction UP/DOWN. History stamps `bid == ask == close` on `OptionQuote` (see `get_historical_atm_straddle`), so `.bid` of a historical quote IS the close.
- `runner.py`: `_BASELINE_SOURCES = ("coin_flip", "always_up")`, `_SURVIVAL_MARGIN_PCT = 2.0`. Survival (for every non-baseline source today): `both_baselines_present AND not TOO_FEW AND avg_return is not None AND avg_return > 0 AND avg_return >= best_baseline_return + 2.0`. The runner iterates `strategies`, scores per source, then finalizes scorecards — it has access to the strategy objects in the first loop, so it can capture `exits_before_event` per source there.
- `strategy.py`: `Strategy` is a Protocol with `predict`. Concrete strategies carry a `source` class attr. `ShortVolStrategy` emits `direction=NONE, sell_straddle=True, confidence=0.5`.
- `scorecard.build_scorecard(source=..., scores=...)` — averages `option_pnl.return_pct` over evaluable scores; no change needed (vol-ramp scores flow through it untouched).
- `alpaca_market.py`: `HistoricalOptionRow` (frozen dataclass: `contract_symbol, strike, expiration_date, option_type, close, open_interest`). `HistoricalOptionReader = Callable[..., list[HistoricalOptionRow]]` with kwargs `underlying_symbol, as_of_date, earnings_date, max_expiration_date`. The reader lists contracts by **expiration window only** (independent of as-of date) and prices each at the bar on/just-before `as_of_date` — so calling the SAME reader twice (entry date, exit date) yields entry and exit closes for the same contract set. `get_historical_atm_straddle` returns `[]` on any missing piece and stamps `bid=ask=close`, `quote_date=as_of_date`. Expiration window filter is `earnings_date <= expiration <= max_expiration_date`.
- `loader.py`: `PointInTimeDataset.bars_as_of(ticker, as_of_date=...)` returns bars sorted ascending, filtered to `<= as_of_date`. `build_event_context` picks exit-ATM quotes via `_atm_quote`. `EventContext` rows are later enriched via `model_copy(update=...)` in the assembler — same mechanism threads the vol-ramp fields.
- `assembler.py`: `as_of_price_for(ticker, report_date, bars)` → `(as_of_date, close)`; `assemble_edge_dataset(*, announcements, bars, option_quotes, target_tickers, horizon_days, peer_window_days)` builds contexts and enriches peer signals via `model_copy`.
- `option_loader.py`: `load_option_quotes_for_events(adapter, *, events, as_of_prices, max_expiration_days)` — per-event try/except skip-not-guess; accumulates `dict[str, list[OptionQuote]]` keyed by ticker.
- `scripts/run_edge_backtest.py`: `_MAX_EXPIRATION_DAYS = 14`; builds `hist_adapter = AlpacaMarketDataAdapter(historical_option_reader=hist_reader)`; computes `as_of_prices` dict keyed `(ticker, report_date)`; strategy list currently `[ReactionAwarePeerStrategy(), ShortVolStrategy(), CoinFlipStrategy(), AlwaysUpStrategy()]`.
- Tests live in `tests/test_edge_option_pnl.py`, `test_edge_strategies.py`, `test_edge_scorer.py`, `test_edge_runner.py`, `test_edge_data_option_loader.py`, `test_alpaca_market.py`, `test_edge_data_assembler.py`. Run with `uv run pytest -q`; lint with `uv run ruff check .`.

## Locked parameters (defaults; sweepable later, per spec "Explicitly deferred")

- **`_ENTRY_LEAD_TRADING_DAYS = 5`** — entry is the trading day 5 trading bars before the exit as-of day (≈ one calendar week before earnings).
- **`_COST_HAIRCUT_PCT = 0.05`** reused — but applied **per side, twice** (buy at `entry*(1+h)`, sell at `exit*(1-h)`) ⇒ ~10% round-trip drag. Deliberately pessimistic for a thin, well-known edge.
- **Survival bar for exit-before-event strategies:** average return must beat **zero (do nothing) + `_SURVIVAL_MARGIN_PCT` (2.0)** and not be `TOO_FEW`. Baselines are still computed and reported as diagnostics, never as the comparator (they hold through earnings and rode market drift — not apples-to-apples).
- **Expiration choice at entry:** within the existing window (`earnings_date <= exp <= earnings_date + 14d`), use the **earliest** expiration, then nearest strike to the entry-day underlying close (ties → lower strike). Earliest-in-window is the contract with the most concentrated earnings vol.

## File structure (all additive)

- Modify `src/prescient/edge/option_pnl.py` — add `simulate_vol_ramp_pnl`.
- Modify `src/prescient/edge/models.py` — `Prediction.buy_vol_ramp`; `EventContext.entry_as_of_date` + four `vol_ramp_*` quote fields.
- Modify `src/prescient/edge/strategy.py` — add `VolRampStrategy` (`exits_before_event = True`).
- Modify `src/prescient/edge/scorer.py` — vol-ramp branch.
- Modify `src/prescient/edge/runner.py` — per-strategy-type survival bar.
- Modify `src/prescient/data/alpaca_market.py` — add `get_historical_vol_ramp_straddle` (reuses the existing injected reader; **no change** to `live_data/alpaca_readers.py`).
- Modify `src/prescient/edge/data/option_loader.py` — add `load_vol_ramp_straddles_for_events`.
- Modify `src/prescient/edge/data/assembler.py` — thread vol-ramp quotes into contexts.
- Modify `scripts/run_edge_backtest.py` — wire the vol-ramp fetch + `VolRampStrategy()`.
- Tests: extend the seven test files named above.

---

### Task 1: Vol-ramp P&L model

**Files:**
- Modify: `src/prescient/edge/option_pnl.py`
- Test: `tests/test_edge_option_pnl.py`

Pure function. Buy the straddle at entry, sell the same contracts at exit, pay the spread haircut on BOTH sides. Theta is implicit (decayed exit value). Loss floored at −100% of premium.

- [ ] **Step 1: Write the failing tests (append to `tests/test_edge_option_pnl.py`)**

```python
def test_vol_ramp_ramped_exit_beats_double_spread() -> None:
    from prescient.edge.option_pnl import simulate_vol_ramp_pnl

    # entry 4.0, exit 6.0, haircut 5% per side.
    # buy cost = 4.0 * 1.05 = 4.2 ; sell proceeds = 6.0 * 0.95 = 5.7
    # net = 5.7 - 4.2 = 1.5 ; return = 1.5 / 4.0 * 100 = 37.5%
    pnl = simulate_vol_ramp_pnl(
        entry_premium=4.0, exit_value=6.0, cost_haircut_pct=0.05
    )
    assert pnl is not None
    assert pnl.entry_premium == 4.0
    assert pnl.exit_value == 6.0
    assert round(pnl.cost_haircut, 4) == round(4.0 * 0.05 + 6.0 * 0.05, 4)  # 0.5
    assert round(pnl.net_pnl, 4) == 1.5
    assert round(pnl.return_pct, 2) == 37.5


def test_vol_ramp_flat_exit_loses_the_double_spread() -> None:
    from prescient.edge.option_pnl import simulate_vol_ramp_pnl

    # entry 4.0, exit 4.0: net = 4.0*0.95 - 4.0*1.05 = -0.4 -> -10.0%
    pnl = simulate_vol_ramp_pnl(
        entry_premium=4.0, exit_value=4.0, cost_haircut_pct=0.05
    )
    assert pnl is not None
    assert round(pnl.net_pnl, 4) == -0.4
    assert round(pnl.return_pct, 2) == -10.0


def test_vol_ramp_decayed_exit_is_negative_but_floored() -> None:
    from prescient.edge.option_pnl import simulate_vol_ramp_pnl

    # Massive decay cannot lose more than the premium paid.
    pnl = simulate_vol_ramp_pnl(
        entry_premium=4.0, exit_value=0.01, cost_haircut_pct=0.05
    )
    assert pnl is not None
    assert pnl.net_pnl >= -4.0
    assert pnl.return_pct >= -100.0


def test_vol_ramp_zero_haircut_is_pure_difference() -> None:
    from prescient.edge.option_pnl import simulate_vol_ramp_pnl

    pnl = simulate_vol_ramp_pnl(
        entry_premium=2.0, exit_value=3.0, cost_haircut_pct=0.0
    )
    assert pnl is not None
    assert round(pnl.net_pnl, 4) == 1.0
    assert round(pnl.return_pct, 2) == 50.0


def test_vol_ramp_invalid_inputs_return_none() -> None:
    from prescient.edge.option_pnl import simulate_vol_ramp_pnl

    assert simulate_vol_ramp_pnl(
        entry_premium=0.0, exit_value=3.0, cost_haircut_pct=0.05
    ) is None
    assert simulate_vol_ramp_pnl(
        entry_premium=-1.0, exit_value=3.0, cost_haircut_pct=0.05
    ) is None
    assert simulate_vol_ramp_pnl(
        entry_premium=2.0, exit_value=0.0, cost_haircut_pct=0.05
    ) is None
    assert simulate_vol_ramp_pnl(
        entry_premium=2.0, exit_value=-1.0, cost_haircut_pct=0.05
    ) is None
```

- [ ] **Step 2: Run to verify failure**

`uv run pytest tests/test_edge_option_pnl.py -q` — expect `ImportError: cannot import name 'simulate_vol_ramp_pnl'`.

- [ ] **Step 3: Implement (append to `src/prescient/edge/option_pnl.py`)**

```python
def simulate_vol_ramp_pnl(
    *,
    entry_premium: float,
    exit_value: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    """Hypothetical pre-earnings vol-ramp trade: BUY the ATM straddle ~1 week out,
    SELL the same contracts the day before the report. Never holds through the
    event, so it cannot eat IV crush and never predicts direction.

    Honesty model: the spread is crossed TWICE — buy at entry_premium*(1+h), sell
    at exit_value*(1-h). Theta is implicit in the exit value. Loss floored at
    -100% of premium. Returns None on non-positive entry premium or exit value.
    """
    if entry_premium <= 0 or exit_value <= 0:
        return None

    buy_cost = entry_premium * (1.0 + cost_haircut_pct)
    sell_proceeds = exit_value * (1.0 - cost_haircut_pct)
    cost_haircut = entry_premium * cost_haircut_pct + exit_value * cost_haircut_pct
    net_pnl = sell_proceeds - buy_cost
    if net_pnl < -entry_premium:
        net_pnl = -entry_premium
    return OptionPnl(
        entry_premium=entry_premium,
        exit_value=exit_value,
        cost_haircut=cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / entry_premium) * 100.0,
    )
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_edge_option_pnl.py -q`
- [ ] **Step 5: Commit** — `git add src/prescient/edge/option_pnl.py tests/test_edge_option_pnl.py && git commit -m "feat(edge): vol-ramp P&L model with double-spread haircut"`

---

### Task 2: Model fields

**Files:**
- Modify: `src/prescient/edge/models.py`
- Test: `tests/test_edge_models.py` (or wherever Prediction/EventContext construction is tested; create the file if absent)

- [ ] **Step 1: Failing tests**

```python
from datetime import date

from prescient.edge.models import (
    EventContext,
    OptionQuote,
    Prediction,
    PredictionDirection,
)


def _quote(option_type: str, quote_date: date) -> OptionQuote:
    return OptionQuote(
        ticker="MU", option_type=option_type, strike=100.0,
        expiration_date=date(2026, 7, 3), quote_date=quote_date,
        bid=2.0, ask=2.0,
    )


def test_prediction_buy_vol_ramp_defaults_false() -> None:
    p = Prediction(
        ticker="MU", as_of_date=date(2026, 6, 23),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="x",
    )
    assert p.buy_vol_ramp is False


def test_event_context_vol_ramp_fields_default_none() -> None:
    ctx = EventContext(
        ticker="MU", earnings_date=date(2026, 6, 24),
        as_of_date=date(2026, 6, 23), underlying_price=100.0,
    )
    assert ctx.entry_as_of_date is None
    assert ctx.vol_ramp_entry_call is None
    assert ctx.vol_ramp_entry_put is None
    assert ctx.vol_ramp_exit_call is None
    assert ctx.vol_ramp_exit_put is None


def test_event_context_accepts_vol_ramp_quotes() -> None:
    entry_d, exit_d = date(2026, 6, 16), date(2026, 6, 23)
    ctx = EventContext(
        ticker="MU", earnings_date=date(2026, 6, 24),
        as_of_date=exit_d, underlying_price=100.0,
        entry_as_of_date=entry_d,
        vol_ramp_entry_call=_quote("CALL", entry_d),
        vol_ramp_entry_put=_quote("PUT", entry_d),
        vol_ramp_exit_call=_quote("CALL", exit_d),
        vol_ramp_exit_put=_quote("PUT", exit_d),
    )
    assert ctx.vol_ramp_entry_call.strike == ctx.vol_ramp_exit_call.strike
```

- [ ] **Step 2: Run to verify failure** (unknown field → pydantic `extra="forbid"` error / AttributeError)
- [ ] **Step 3: Implement** — in `models.py`:
  - `Prediction`: add `buy_vol_ramp: bool = False` after `sell_straddle`.
  - `EventContext`: add after `atm_put`:

```python
    # Pre-earnings vol-ramp fields (strike-locked; see vol-ramp spec).
    # entry_* are stamped entry_as_of_date; exit_* price the SAME strike+expiration
    # at as_of_date. The existing atm_call/atm_put stay the exit-ATM quotes used
    # for the implied move and the through-earnings strategies.
    entry_as_of_date: date | None = None
    vol_ramp_entry_call: OptionQuote | None = None
    vol_ramp_entry_put: OptionQuote | None = None
    vol_ramp_exit_call: OptionQuote | None = None
    vol_ramp_exit_put: OptionQuote | None = None
```

- [ ] **Step 4: Run to verify pass**, plus full suite (`uv run pytest -q`) — existing construction must be unaffected.
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): vol-ramp prediction flag + strike-locked entry/exit context fields"`

---

### Task 3: VolRampStrategy

**Files:**
- Modify: `src/prescient/edge/strategy.py`
- Test: `tests/test_edge_strategies.py`

- [ ] **Step 1: Failing tests**

```python
def test_vol_ramp_strategy_emits_non_directional_vol_ramp_prediction() -> None:
    from prescient.edge.strategy import VolRampStrategy

    strategy = VolRampStrategy()
    prediction = strategy.predict(_context())  # reuse the file's context helper
    assert prediction.direction == PredictionDirection.NONE
    assert prediction.buy_vol_ramp is True
    assert prediction.sell_straddle is False
    assert prediction.confidence == 0.5
    assert prediction.source == "vol_ramp"


def test_vol_ramp_strategy_declares_exit_before_event() -> None:
    from prescient.edge.strategy import VolRampStrategy

    assert VolRampStrategy.exits_before_event is True
    # Existing strategies implicitly hold through the event.
    from prescient.edge.strategy import ReactionAwarePeerStrategy, ShortVolStrategy

    assert getattr(ReactionAwarePeerStrategy, "exits_before_event", False) is False
    assert getattr(ShortVolStrategy, "exits_before_event", False) is False
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement (append to `strategy.py`)**

```python
class VolRampStrategy:
    """Direction-free pre-earnings vol-ramp: buy the ATM straddle ~5 trading days
    before the report, sell the SAME contracts the day before. Exits before the
    event by construction (never eats IV crush, never predicts direction)."""

    source = "vol_ramp"
    exits_before_event = True

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
            buy_vol_ramp=True,
        )
```

- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): VolRampStrategy (exits before event)"`

---

### Task 4: Scorer vol-ramp branch

**Files:**
- Modify: `src/prescient/edge/scorer.py`
- Test: `tests/test_edge_scorer.py`

Branch order in `score_event`: check `prediction.buy_vol_ramp` FIRST (before `sell_straddle`). Keep the existing realized/implied early-returns untouched (sample alignment across strategies; implied/realized stay as diagnostics on the score). When any of the four `vol_ramp_*` quotes is missing → `evaluable=False, not_evaluable_reason="missing_vol_ramp_straddle"`. Entry premium = `vol_ramp_entry_call.bid + vol_ramp_entry_put.bid`; exit value = `vol_ramp_exit_call.bid + vol_ramp_exit_put.bid` (history stamps bid == ask == close). `direction_correct`, `beat_implied`, `stayed_within_implied` stay `None`.

- [ ] **Step 1: Failing tests** (use the file's existing context/quote helpers; key cases)

```python
def test_score_event_vol_ramp_computes_pnl_from_entry_and_exit_straddles() -> None:
    # entry call+put closes 2.0+2.0=4.0 ; exit closes 3.0+3.0=6.0 ; haircut 5%/side
    # net = 6*0.95 - 4*1.05 = 1.5 -> 37.5% on premium
    ...
    score = score_event(prediction=vol_ramp_prediction, context=ctx)
    assert score.evaluable is True
    assert score.direction_correct is None
    assert score.beat_implied is None
    assert score.stayed_within_implied is None
    assert score.option_pnl is not None
    assert round(score.option_pnl.return_pct, 2) == 37.5


def test_score_event_vol_ramp_missing_entry_leg_not_evaluable() -> None:
    # context with vol_ramp_entry_put=None
    score = score_event(prediction=vol_ramp_prediction, context=ctx)
    assert score.evaluable is False
    assert score.not_evaluable_reason == "missing_vol_ramp_straddle"


def test_score_event_directional_and_sell_vol_branches_unchanged() -> None:
    # NO-REGRESSION: same contexts as existing tests, with vol_ramp_* fields left
    # None; assert UP/DOWN and sell_straddle scores are byte-identical to before.
    ...
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** — in `score_event`, after the implied-move guard, insert before the `sell_straddle` branch:

```python
    if prediction.buy_vol_ramp:
        legs = (
            context.vol_ramp_entry_call,
            context.vol_ramp_entry_put,
            context.vol_ramp_exit_call,
            context.vol_ramp_exit_put,
        )
        if any(leg is None or leg.bid is None for leg in legs):
            return EventScore(
                ticker=context.ticker,
                as_of_date=context.as_of_date,
                source=prediction.source,
                evaluable=False,
                not_evaluable_reason="missing_vol_ramp_straddle",
                confidence=prediction.confidence,
            )
        entry_premium = (
            context.vol_ramp_entry_call.bid + context.vol_ramp_entry_put.bid
        )
        exit_value = (
            context.vol_ramp_exit_call.bid + context.vol_ramp_exit_put.bid
        )
        option_pnl = simulate_vol_ramp_pnl(
            entry_premium=entry_premium,
            exit_value=exit_value,
            cost_haircut_pct=_COST_HAIRCUT_PCT,
        )
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=option_pnl is not None,
            not_evaluable_reason=(
                None if option_pnl is not None else "invalid_vol_ramp_pnl"
            ),
            implied_move_pct=implied.implied_move_pct,   # diagnostic only
            realized_move_pct=realized_pct,              # diagnostic only
            option_pnl=option_pnl,
            confidence=prediction.confidence,
        )
```

(Import `simulate_vol_ramp_pnl` alongside the existing two.)

- [ ] **Step 4: Run to verify pass + full suite** (no-regression test is the gate)
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): scorer branch for vol-ramp (strike-locked entry/exit, no direction)"`

---

### Task 5: Runner survival bar by strategy type

**Files:**
- Modify: `src/prescient/edge/runner.py`
- Test: `tests/test_edge_runner.py`

In the scoring loop, capture `pre_event_sources = {source for strategies with getattr(s, "exits_before_event", False)}`. In finalization: sources in `pre_event_sources` survive iff `not TOO_FEW AND avg_return is not None AND avg_return > 0 AND avg_return >= 0.0 + _SURVIVAL_MARGIN_PCT`. Baselines are NOT the comparator (note appended to the scorecard either way: `"Pre-event strategy: survival bar is do-nothing (zero) + margin; baselines shown as diagnostics only (they hold through earnings)."`). Through-earnings sources keep today's gate **exactly** (regression test required). `both_baselines_present` is not required for pre-event survival, but keep computing it for the others.

- [ ] **Step 1: Failing tests**

```python
def test_pre_event_strategy_survives_on_do_nothing_bar() -> None:
    # avg return +5% (> 0 + 2.0 margin), >= 30 evaluable events -> survived=True
    # even when always_up baseline avg is +20% (drift) — baselines are diagnostics.
    ...


def test_pre_event_strategy_negative_return_does_not_survive() -> None:
    ...


def test_pre_event_strategy_below_margin_does_not_survive() -> None:
    # avg +1.0% < 2.0 margin over zero -> survived=False
    ...


def test_through_earnings_survival_verdicts_unchanged() -> None:
    # REGRESSION: rerun the existing fixture sets for reaction_aware_peer and
    # short_vol; assert identical survived/notes as before the change.
    ...
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** (keep the existing return-denominator NOTE comment; add a sibling note explaining the pre-event bar)
- [ ] **Step 4: Run to verify pass + full suite**
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): do-nothing survival bar for exit-before-event strategies"`

---

### Task 6: Adapter — strike-locked entry/exit straddle fetch

**Files:**
- Modify: `src/prescient/data/alpaca_market.py`
- Test: `tests/test_alpaca_market.py`

`get_historical_vol_ramp_straddle` reuses `self._historical_option_reader` — called twice: once with `as_of_date=entry_as_of_date`, once with `as_of_date=exit_as_of_date` (same expiration window args). **No change to `live_data/alpaca_readers.py`.** From the ENTRY rows: filter to in-window rows with non-None close; pick the **earliest expiration**, then the strike nearest `entry_underlying_price` (ties → lower strike). Require all four legs (entry CALL/PUT from entry rows; exit CALL/PUT from exit rows, same strike+expiration, non-None close) else return `[]`. Return four `OptionQuote`s stamped with their respective dates, `bid = ask = close`.

- [ ] **Step 1: Failing tests** (inject a fake reader; follow the file's existing fake-reader pattern)

```python
def test_vol_ramp_straddle_returns_four_strike_locked_quotes() -> None:
    # Fake reader returns CALL/PUT rows at strikes 95/100/105 for exp 2026-07-03;
    # entry price 99.7 -> ATM 100. Entry closes 2.0/2.1, exit closes 3.0/3.2.
    quotes = adapter.get_historical_vol_ramp_straddle(
        underlying_symbol="MU",
        entry_as_of_date=date(2026, 6, 16),
        exit_as_of_date=date(2026, 6, 23),
        entry_underlying_price=99.7,
        earnings_date=date(2026, 6, 24),
        max_expiration_date=date(2026, 7, 8),
    )
    assert [q.quote_date for q in quotes] == [
        date(2026, 6, 16), date(2026, 6, 16),
        date(2026, 6, 23), date(2026, 6, 23),
    ]
    assert {q.strike for q in quotes} == {100.0}
    assert {q.expiration_date for q in quotes} == {date(2026, 7, 3)}
    assert [q.option_type for q in quotes] == ["CALL", "PUT", "CALL", "PUT"]


def test_vol_ramp_straddle_picks_earliest_expiration_in_window() -> None: ...
def test_vol_ramp_straddle_missing_exit_leg_returns_empty() -> None: ...
def test_vol_ramp_straddle_missing_entry_close_returns_empty() -> None: ...
def test_vol_ramp_straddle_no_reader_records_error_returns_empty() -> None: ...
def test_vol_ramp_straddle_reader_exception_returns_empty() -> None: ...
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** (mirror `get_historical_atm_straddle`'s structure: reader-None guard via `_record`, try/except `_classify`, in-window + close filters, then the earliest-expiration/nearest-strike pick and the four-quote build)
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit** — `git commit -m "feat(data): strike-locked entry/exit vol-ramp straddle fetch (reuses reader)"`

---

### Task 7: Loader — vol-ramp straddles per event

**Files:**
- Modify: `src/prescient/edge/data/option_loader.py`
- Test: `tests/test_edge_data_option_loader.py`

```python
def load_vol_ramp_straddles_for_events(
    adapter: Any,
    *,
    events: Sequence[EarningsAnnouncement],
    as_of_prices: dict[tuple[str, date], tuple[date, float]],
    bars: dict[str, list[DailyBarSnapshot]],
    entry_lead_trading_days: int,
    max_expiration_days: int,
) -> dict[tuple[str, date], list[OptionQuote]]:
```

Per event: look up `(exit_as_of_date, _)` from `as_of_prices` (skip if absent). Compute the entry bar from `PointInTimeDataset(bars=bars, option_quotes={}).bars_as_of(ticker, as_of_date=exit_as_of_date)`: need `len(visible) > entry_lead_trading_days`; entry bar = `visible[-(entry_lead_trading_days + 1)]`; skip if its `close` is None. Call `adapter.get_historical_vol_ramp_straddle(...)` inside try/except (skip-not-guess). Only keep results with exactly 4 quotes. Key output by `(ticker, report_date)`.

- [ ] **Step 1: Failing tests** — happy path (4 quotes keyed correctly, entry date = 5 trading days back), too-little-bar-history skip, missing as-of-price skip, adapter-exception skip, `[]`-result skip.
- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): vol-ramp straddle loader (entry day from trading-bar count)"`

---

### Task 8: Assembler threading

**Files:**
- Modify: `src/prescient/edge/data/assembler.py`
- Test: `tests/test_edge_data_assembler.py`

Add parameter `vol_ramp_quotes: dict[tuple[str, date], list[OptionQuote]] | None = None` to `assemble_edge_dataset` (default None → behavior unchanged). After the peer-signal `model_copy`, when the event has four quotes under `(ann.ticker, ann.report_date)`, enrich the context:

```python
entry_call, entry_put, exit_call, exit_put = quotes
ctx = ctx.model_copy(update={
    "entry_as_of_date": entry_call.quote_date,
    "vol_ramp_entry_call": entry_call,
    "vol_ramp_entry_put": entry_put,
    "vol_ramp_exit_call": exit_call,
    "vol_ramp_exit_put": exit_put,
})
```

No-lookahead: entry quotes are stamped on/before `as_of_date` by construction; assert in a test that `entry_as_of_date < as_of_date < earnings_date`. Existing `atm_call`/`atm_put` untouched.

- [ ] **Step 1: Failing tests** — threading happy path; `vol_ramp_quotes=None` leaves contexts identical (regression); event without quotes gets None fields.
- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify pass + full suite**
- [ ] **Step 5: Commit** — `git commit -m "feat(edge): assembler threads strike-locked vol-ramp quotes into contexts"`

---

### Task 9: Wire the live script

**Files:**
- Modify: `scripts/run_edge_backtest.py`

- [ ] **Step 1:** Add `_ENTRY_LEAD_TRADING_DAYS = 5` constant. After the existing `load_option_quotes_for_events` call, add the vol-ramp fetch (`load_vol_ramp_straddles_for_events(hist_adapter, events=target_events, as_of_prices=as_of_prices, bars=bars, entry_lead_trading_days=_ENTRY_LEAD_TRADING_DAYS, max_expiration_days=_MAX_EXPIRATION_DAYS)`), print its coverage count, pass `vol_ramp_quotes=...` into `assemble_edge_dataset`, and add `VolRampStrategy()` to the strategy list (import it).
- [ ] **Step 2:** `uv run ruff check .` and `uv run pytest -q` — both green.
- [ ] **Step 3: Commit** — `git commit -m "feat(edge): include VolRampStrategy in the live backtest scorecard"`

---

### Task 10: Sync the spec with the strike-locked resolution

**Files:**
- Modify: `docs/superpowers/specs/2026-06-07-pre-earnings-vol-ramp-design.md`

- [ ] **Step 1:** Update §2 (models), §4 (scorer), §6 (data assembly) to the four `vol_ramp_*` fields + `(ticker, report_date)`-keyed loader actually implemented, and note that `live_data/alpaca_readers.py` needed no change (the existing reader is called twice). Add a line to the changelog/status: "Implemented 2026-06-10; spec synced to strike-locked context fields."
- [ ] **Step 2: Commit** — `git commit -m "docs: sync vol-ramp spec with strike-locked implementation"`

---

### Task 11: Live run + verdict (the whole point)

This is the manual validation gate — real Alpha Vantage + Alpaca data.

- [ ] **Step 1: Smoke test** — `uv run python scripts/run_edge_backtest.py --limit 20`. Expect a `vol_ramp` row in the scorecard; some events may be `missing_vol_ramp_straddle` (thin option-bar history at entry) — that is honest coverage, not a bug.
- [ ] **Step 2: Full run** — `uv run python scripts/run_edge_backtest.py`. Record: evaluable count, avg/median return, sample-size verdict, survived, and the do-nothing-bar note.
- [ ] **Step 3: Record the verdict** in `docs/program/2026-06-08-prescient-program-review.md`: update §4 (experiments table), §6 (add §6.3 results), and §9 (where we are). Whatever the verdict, deliver it with the sample-size label.
- [ ] **Step 4: Commit** — `git commit -m "docs(program): vol-ramp backtest verdict"`

---

## Red flags for the implementer

- Never weaken the through-earnings survival gate; the do-nothing bar applies ONLY to `exits_before_event = True` strategies. The regression tests in Tasks 4/5 are the contract.
- Never read any post-event price in the vol-ramp path (entry and exit are both strictly before `earnings_date`).
- Skip-not-guess everywhere in the data layer: a missing leg/close/contract drops the event for vol_ramp only; other strategies still score it.
- This is propose-only research tooling. Nothing in this plan places, sizes, authorizes, or recommends a trade (CLAUDE.md hard rules apply in full).
