# Short-Vol Defined-Risk Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-directional short-volatility strategy + an honest capped-short-straddle P&L model to the existing edge harness, so the backtest can test whether the volatility risk premium is harvestable by a small account via a defined-risk, unhedged, sell-and-hold short straddle around earnings.

**Architecture:** Additive only — a new pure `simulate_capped_short_straddle_pnl` beside the existing buy-side model, a `sell_straddle` flag on `Prediction` + `stayed_within_implied` on `EventScore`, a `ShortVolStrategy`, a sell-vol branch in the scorer, a runner survival rule generalized to the average-return axis (so it is well-defined for a non-directional strategy), and `ShortVolStrategy` added to the live script. Nothing existing is rewritten; directional strategies must show no regression.

**Tech Stack:** Python >=3.11, Pydantic v2 (frozen, extra="forbid"), pytest, ruff (line-length 100), uv. Reuses `prescient.edge` (models, scorer, runner, strategy, implied_move) and `OptionPnl`.

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-06-short-vol-defined-risk-design.md` (read it first,
incl. the "Critical interpretation rule" — this tests the RETAIL unhedged version).

## Verified facts about the existing code

- `Prediction` (`src/prescient/edge/models.py`): frozen, fields `ticker, as_of_date: date,
  direction: PredictionDirection, predicted_move_pct: float, confidence: float
  (ge=0,le=1), source: str`.
- `EventScore` (same file): frozen, fields `ticker, as_of_date, source, evaluable: bool,
  not_evaluable_reason, direction_correct, beat_implied, implied_move_pct,
  realized_move_pct, option_pnl: OptionPnl|None, confidence`.
- `OptionPnl` (same file): frozen, `entry_premium, exit_value, cost_haircut, net_pnl,
  return_pct` (all float).
- `simulate_option_pnl(*, direction, strike, entry_premium, post_report_close,
  cost_haircut_pct)` in `option_pnl.py` — the BUY model; leave it untouched.
- `scorer.score_event(*, prediction, context)` — builds the buy-side `option_pnl` only
  for UP/DOWN. `_COST_HAIRCUT_PCT = 0.05`. `compute_implied_move(...)` returns an
  `ImpliedMove` with `.implied_move_pct` (positive %) and `.straddle_price`
  (call_mid + put_mid). `context.realized_move.realized_move_pct` is signed %;
  `context.realized_move.post_report_close` and `context.underlying_price` are prices.
- `runner.run_edge_backtest(*, contexts, strategies)`. Constants `_BASELINE_SOURCES =
  ("coin_flip","always_up")`, `_SURVIVAL_MARGIN_PCT = 2.0`. Current survival requires
  `both_baselines_present AND beat_implied_rate is not None AND not TOO_FEW AND
  beat_implied_rate >= best_baseline_rate + margin AND avg_return is not None AND
  avg_return > 0`. We generalize the comparison axis from beat-implied-rate to
  average-return.
- `StrategyScorecard` has `average_option_return_pct` (mean of evaluable `option_pnl.
  return_pct`) and `beat_implied_rate`.
- `strategy.py`: `Strategy` Protocol + `AlwaysUpStrategy/CoinFlipStrategy/
  ReactionAwarePeerStrategy`, each with a `source` attr and `predict(context) ->
  Prediction`.
- Live script `scripts/run_edge_backtest.py` passes
  `strategies=[ReactionAwarePeerStrategy(), CoinFlipStrategy(), AlwaysUpStrategy()]`.

## Locked parameters (defaults; sweepable later)

- **`_DEFAULT_RISK_WIDTH_W = 5.0`** — capital-at-risk per trade in $ (per 1 straddle).
  Small and account-appropriate; the loss floor.
- **Wing-cost model:** `wing_cost = min(credit, credit * (straddle_price / (2 * W)))`
  clamped so `0 <= wing_cost <= credit`. This scales INVERSELY with W (tighter cap =
  larger fraction of credit spent on wings) and never exceeds the credit. Rationale: a
  larger W (wider protection) is cheaper relative to the credit; a tight W eats most of
  it. (A deliberately simple, monotonic approximation — not a Black-Scholes wing price —
  sufficient to enforce the "no free protection" honesty property.)
- **`_COST_HAIRCUT_PCT = 0.05`** reused from the scorer for the bid/ask haircut.

## File structure (all additive)

- Modify `src/prescient/edge/option_pnl.py` — add `simulate_capped_short_straddle_pnl`.
- Modify `src/prescient/edge/models.py` — `Prediction.sell_straddle: bool = False`;
  `EventScore.stayed_within_implied: bool | None = None`.
- Modify `src/prescient/edge/strategy.py` — add `ShortVolStrategy`.
- Modify `src/prescient/edge/scorer.py` — sell-vol branch.
- Modify `src/prescient/edge/runner.py` — generalize survival to average-return axis.
- Modify `scripts/run_edge_backtest.py` — add `ShortVolStrategy()` to the list.
- Tests: extend `test_edge_option_pnl.py`, `test_edge_strategies.py`,
  `test_edge_scorer.py`, `test_edge_runner.py`.

---

### Task 1: Capped-short-straddle P&L model

**Files:**
- Modify: `src/prescient/edge/option_pnl.py`
- Test: `tests/test_edge_option_pnl.py`

A pure function modeling SELLING the ATM straddle with a defined-risk wing cap. Credit =
straddle price; payout owed = absolute $ move beyond the strike; wing cost scales
inversely with W; net floored at `-W`; return measured on W.

- [ ] **Step 1: Write the failing tests (append to tests/test_edge_option_pnl.py)**

```python
def test_capped_short_small_move_keeps_credit_minus_wings() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # straddle credit 8.0, stock moved $2 (strike 100 -> 102), W=5, haircut 0.
    # wing_cost = 8 * (8 / (2*5)) = 8*0.8 = 6.4. payout owed = |102-100| = 2.0.
    # net = 8 - 6.4 - 2.0 = -0.4 -> small loss, NOT floored (within -5).
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=102.0, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert pnl.entry_premium == 8.0
    assert round(pnl.net_pnl, 2) == -0.4
    # return measured on W (5.0): -0.4 / 5 * 100 = -8%
    assert round(pnl.return_pct, 1) == -8.0


def test_capped_short_tiny_move_is_profitable() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # credit 8, stock barely moved ($0.5). wing 6.4, payout 0.5 -> net 1.1 WIN.
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert round(pnl.net_pnl, 2) == 1.1
    assert pnl.net_pnl > 0


def test_capped_short_big_move_loss_floored_at_minus_W() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # stock moved $30 -> payout would be huge, but loss is floored at -W = -5.
    pnl = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=130.0, risk_width=5.0, cost_haircut_pct=0.0,
    )
    assert pnl is not None
    assert pnl.net_pnl == -5.0          # floored at -W exactly
    assert pnl.return_pct == -100.0     # -5 / 5 * 100


def test_capped_short_tighter_W_costs_more_wings() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    # Same tiny move; compare W=5 vs W=10. Tighter cap (W=5) -> bigger wing cost
    # -> smaller net credit than the wider W=10.
    tight = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=5.0, cost_haircut_pct=0.0,
    )
    wide = simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=100.5, risk_width=10.0, cost_haircut_pct=0.0,
    )
    assert tight is not None and wide is not None
    assert wide.net_pnl > tight.net_pnl  # wider cap = cheaper wings = more profit


def test_capped_short_invalid_inputs_return_none() -> None:
    from prescient.edge.option_pnl import simulate_capped_short_straddle_pnl

    assert simulate_capped_short_straddle_pnl(
        straddle_price=0.0, strike=100.0, underlying_price=100.0,
        post_report_close=101.0, risk_width=5.0, cost_haircut_pct=0.0,
    ) is None
    assert simulate_capped_short_straddle_pnl(
        straddle_price=8.0, strike=100.0, underlying_price=100.0,
        post_report_close=101.0, risk_width=0.0, cost_haircut_pct=0.0,
    ) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_edge_option_pnl.py -k capped_short -v`
Expected: FAIL with `ImportError` / `cannot import name 'simulate_capped_short_straddle_pnl'`

- [ ] **Step 3: Implement (append to src/prescient/edge/option_pnl.py)**

```python
def simulate_capped_short_straddle_pnl(
    *,
    straddle_price: float,
    strike: float,
    underlying_price: float,
    post_report_close: float,
    risk_width: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    """Hypothetical DEFINED-RISK short straddle (sell the ATM straddle, cap the loss
    at `risk_width` W via protective wings whose cost is modeled honestly).

    credit       = straddle_price (premium received for selling)
    wing_cost    = credit * min(1.0, straddle_price / (2 * W))  -- scales INVERSELY
                   with W (tighter cap = costlier wings), never exceeds the credit.
    payout       = |post_report_close - strike|  (what the short straddle owes)
    net          = credit - wing_cost - payout - bid/ask haircut, FLOORED at -W.
    return_pct   = net / W * 100  (return on capital-at-risk, not on premium).

    Returns None on invalid inputs (non-positive credit, strike, or W). The bid/ask
    haircut is applied to the credit (cost of getting in/out). This is the RETAIL,
    UNHEDGED, sell-and-hold version (no delta-hedging modeled)."""
    if straddle_price <= 0 or strike <= 0 or risk_width <= 0:
        return None

    credit = straddle_price
    wing_cost = credit * min(1.0, straddle_price / (2.0 * risk_width))
    payout = abs(post_report_close - strike)
    cost_haircut = credit * cost_haircut_pct
    net_pnl = credit - wing_cost - payout - cost_haircut
    if net_pnl < -risk_width:
        net_pnl = -risk_width
    return OptionPnl(
        entry_premium=credit,
        exit_value=payout,
        cost_haircut=wing_cost + cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / risk_width) * 100.0,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_edge_option_pnl.py -v`
Expected: PASS (existing buy-side tests + 5 new capped-short tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/option_pnl.py tests/test_edge_option_pnl.py
git add src/prescient/edge/option_pnl.py tests/test_edge_option_pnl.py
git commit -m "feat(edge): capped-short-straddle P&L model (defined-risk, honest wings)"
```

---

### Task 2: Prediction.sell_straddle + EventScore.stayed_within_implied

**Files:**
- Modify: `src/prescient/edge/models.py`
- Test: `tests/test_edge_models.py`

Two additive, defaulted fields. Existing construction is unaffected (defaults).

- [ ] **Step 1: Write the failing test (append to tests/test_edge_models.py)**

```python
def test_prediction_sell_straddle_defaults_false_and_settable() -> None:
    from datetime import date
    from prescient.edge.models import Prediction, PredictionDirection

    p = Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="short_vol",
    )
    assert p.sell_straddle is False
    p2 = Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="short_vol", sell_straddle=True,
    )
    assert p2.sell_straddle is True


def test_event_score_stayed_within_implied_defaults_none() -> None:
    from datetime import date
    from prescient.edge.models import EventScore

    s = EventScore(
        ticker="MU", as_of_date=date(2024, 6, 25), source="x", evaluable=False,
    )
    assert s.stayed_within_implied is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_edge_models.py -k "sell_straddle or stayed_within" -v`
Expected: FAIL (`sell_straddle` / `stayed_within_implied` not valid fields → ValidationError or AttributeError).

- [ ] **Step 3: Implement**

In `src/prescient/edge/models.py`, add to `Prediction` (after `source: str`):

```python
    sell_straddle: bool = False
```

And add to `EventScore` (after `confidence: float | None = None`):

```python
    stayed_within_implied: bool | None = None
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_edge_models.py -v`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/models.py tests/test_edge_models.py
git add src/prescient/edge/models.py tests/test_edge_models.py
git commit -m "feat(edge): Prediction.sell_straddle + EventScore.stayed_within_implied"
```

---

### Task 3: ShortVolStrategy

**Files:**
- Modify: `src/prescient/edge/strategy.py`
- Test: `tests/test_edge_strategies.py`

Non-directional: always wants to sell the straddle. `direction=NONE`, `sell_straddle=True`.

- [ ] **Step 1: Write the failing test (append to tests/test_edge_strategies.py)**

```python
def test_short_vol_strategy_is_non_directional_sell() -> None:
    from datetime import date
    from prescient.edge.models import EventContext, PredictionDirection
    from prescient.edge.strategy import ShortVolStrategy

    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0,
    )
    pred = ShortVolStrategy().predict(ctx)
    assert pred.source == "short_vol"
    assert pred.direction == PredictionDirection.NONE
    assert pred.sell_straddle is True
    assert 0.0 <= pred.confidence <= 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_edge_strategies.py -k short_vol -v`
Expected: FAIL with `ImportError: cannot import name 'ShortVolStrategy'`

- [ ] **Step 3: Implement (append to src/prescient/edge/strategy.py)**

```python
class ShortVolStrategy:
    """Non-directional: bets the realized move stays below the implied move, by
    SELLING the ATM straddle (defined-risk in the P&L model). It does not predict
    up/down; it always wants to sell vol when a straddle exists."""

    source = "short_vol"

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
            sell_straddle=True,
        )
```

(`EventContext`, `Prediction`, `PredictionDirection` are already imported in this file.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_edge_strategies.py -v`
Expected: PASS (existing + 1 new).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/strategy.py tests/test_edge_strategies.py
git add src/prescient/edge/strategy.py tests/test_edge_strategies.py
git commit -m "feat(edge): ShortVolStrategy (non-directional defined-risk vol seller)"
```

---

### Task 4: Sell-vol scoring branch

**Files:**
- Modify: `src/prescient/edge/scorer.py`
- Test: `tests/test_edge_scorer.py`

When `prediction.sell_straddle` is True and both ATM legs exist, score via the capped-
short model; set `stayed_within_implied = |realized| < implied`; `option_pnl` becomes the
short trade's P&L. Directional predictions are UNCHANGED (no regression). Pure sell-vol
predictions leave `direction_correct`/`beat_implied` as None (non-directional).

- [ ] **Step 1: Write the failing tests (append to tests/test_edge_scorer.py)**

```python
def test_sell_vol_small_move_scores_short_pnl_and_stayed_within() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    # implied = (4.0 + 4.0)/100 = 8%. realized +3% (inside) -> stayed_within True.
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=103.0, realized_move_pct=3.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                      confidence=0.5, source="short_vol", sell_straddle=True)
    s = score_event(prediction=pred, context=ctx)
    assert s.evaluable is True
    assert s.stayed_within_implied is True       # 3% < 8%
    assert s.option_pnl is not None              # short-straddle P&L present
    assert s.direction_correct is None           # non-directional
    assert s.beat_implied is None


def test_sell_vol_big_move_not_stayed_within_and_capped_loss() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    # realized +20% (outside 8%) -> stayed_within False; loss floored at -W.
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=120.0, realized_move_pct=20.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                      confidence=0.5, source="short_vol", sell_straddle=True)
    s = score_event(prediction=pred, context=ctx)
    assert s.stayed_within_implied is False
    assert s.option_pnl is not None
    assert s.option_pnl.net_pnl < 0              # a big move loses (capped)


def test_directional_scoring_unchanged_no_regression() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=112.0, realized_move_pct=12.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.UP, predicted_move_pct=4.0,
                      confidence=0.55, source="reaction_aware_peer")
    s = score_event(prediction=pred, context=ctx)
    # unchanged behavior: directional fields set, stayed_within_implied stays None
    assert s.direction_correct is True
    assert s.beat_implied is True
    assert s.stayed_within_implied is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_edge_scorer.py -k "sell_vol or no_regression" -v`
Expected: FAIL (sell-vol path not implemented; `stayed_within_implied` always None).

- [ ] **Step 3: Implement**

In `src/prescient/edge/scorer.py`, update the import line:

```python
from prescient.edge.option_pnl import (
    simulate_capped_short_straddle_pnl,
    simulate_option_pnl,
)
```

Add a module constant near `_COST_HAIRCUT_PCT`:

```python
_DEFAULT_RISK_WIDTH_W = 5.0
```

Then, in `score_event`, AFTER `realized_pct = realized.realized_move_pct` and the
directional `direction_correct`/`beat_implied`/`option_pnl` blocks, insert the sell-vol
branch and a `stayed_within_implied` computation. Replace the existing tail of the
function (from the `option_pnl = None` directional block through the final `return`) with:

```python
    direction_correct: bool | None = None
    if prediction.direction == PredictionDirection.UP:
        direction_correct = realized_pct > 0
    elif prediction.direction == PredictionDirection.DOWN:
        direction_correct = realized_pct < 0

    beat_implied: bool | None = None
    if prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
        on_predicted_side = (
            realized_pct > 0
            if prediction.direction == PredictionDirection.UP
            else realized_pct < 0
        )
        beat_implied = on_predicted_side and (
            abs(realized_pct) >= implied.implied_move_pct
        )

    stayed_within_implied: bool | None = None
    option_pnl = None
    strike = context.atm_call.strike if context.atm_call is not None else None

    if prediction.sell_straddle:
        # Non-directional defined-risk short straddle.
        stayed_within_implied = abs(realized_pct) < implied.implied_move_pct
        if strike is not None:
            option_pnl = simulate_capped_short_straddle_pnl(
                straddle_price=implied.straddle_price,
                strike=strike,
                underlying_price=context.underlying_price,
                post_report_close=realized.post_report_close,
                risk_width=_DEFAULT_RISK_WIDTH_W,
                cost_haircut_pct=_COST_HAIRCUT_PCT,
            )
    elif prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
        if strike is not None:
            option_pnl = simulate_option_pnl(
                direction=prediction.direction.name,  # "UP"/"DOWN"
                strike=strike,
                entry_premium=implied.straddle_price / 2.0,
                post_report_close=realized.post_report_close,
                cost_haircut_pct=_COST_HAIRCUT_PCT,
            )

    return EventScore(
        ticker=context.ticker,
        as_of_date=context.as_of_date,
        source=prediction.source,
        evaluable=True,
        direction_correct=direction_correct,
        beat_implied=beat_implied,
        implied_move_pct=implied.implied_move_pct,
        realized_move_pct=realized_pct,
        option_pnl=option_pnl,
        confidence=prediction.confidence,
        stayed_within_implied=stayed_within_implied,
    )
```

(Note: this preserves the directional path verbatim and adds the sell-vol branch; the
directional `option_pnl` block is now inside the `elif`.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_edge_scorer.py -v`
Expected: PASS (all existing scorer tests + 3 new).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/scorer.py tests/test_edge_scorer.py
git add src/prescient/edge/scorer.py tests/test_edge_scorer.py
git commit -m "feat(edge): sell-vol scoring branch (capped short straddle + stayed_within)"
```

---

### Task 5: Generalize the runner survival rule to the average-return axis

**Files:**
- Modify: `src/prescient/edge/runner.py`
- Test: `tests/test_edge_runner.py`

Make survival well-defined for a non-directional strategy: compare AVERAGE RETURN (which
every strategy has) to the baselines, instead of beat-implied-rate. Directional
strategies' bar stays at least as strict. A regression test asserts a losing strategy
still does not survive.

- [ ] **Step 1: Write the failing tests (append to tests/test_edge_runner.py)**

```python
def test_short_vol_survives_when_beats_baselines_on_return() -> None:
    from datetime import date, timedelta
    from prescient.edge.models import Prediction, PredictionDirection
    from prescient.edge.runner import run_edge_backtest

    # Strategy whose avg return clearly beats both baselines, with enough events.
    class WinVol:
        source = "short_vol"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                              confidence=0.5, source=self.source, sell_straddle=True)

    class FlipDown:
        source = "coin_flip"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.DOWN, predicted_move_pct=0.0,
                              confidence=0.5, source=self.source)

    class Up:
        source = "always_up"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.UP, predicted_move_pct=0.0,
                              confidence=0.5, source=self.source)

    # tiny moves every time -> short vol profits, directional baselines lose to IV crush
    contexts = [_ctx("MU", 0.5, date(2024, 1, 1) + timedelta(days=i)) for i in range(200)]
    result = run_edge_backtest(contexts=contexts, strategies=[WinVol(), FlipDown(), Up()])
    card = result.scorecards["short_vol"]
    assert card.average_option_return_pct is not None
    assert card.survived is True


def test_losing_directional_still_does_not_survive_under_generalized_rule() -> None:
    from datetime import date, timedelta
    from prescient.edge.models import Prediction, PredictionDirection
    from prescient.edge.runner import run_edge_backtest

    # The read-through-style losing case must STILL be survived=False after the change.
    class AlwaysUpPredict:
        source = "reaction_aware_peer"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.UP, predicted_move_pct=10.0,
                              confidence=0.8, source=self.source)

    class Flip:
        source = "coin_flip"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.UP, predicted_move_pct=0.0,
                              confidence=0.5, source=self.source)

    class Up:
        source = "always_up"
        def predict(self, context):
            return Prediction(ticker=context.ticker, as_of_date=context.as_of_date,
                              direction=PredictionDirection.UP, predicted_move_pct=0.0,
                              confidence=0.5, source=self.source)

    # mostly-down realized -> long calls lose; reaction_aware_peer should NOT survive
    contexts = []
    for i in range(200):
        pct = -8.0 if i % 4 else -2.0
        contexts.append(_ctx("MU", pct, date(2024, 1, 1) + timedelta(days=i)))
    result = run_edge_backtest(
        contexts=contexts, strategies=[AlwaysUpPredict(), Flip(), Up()])
    assert result.scorecards["reaction_aware_peer"].survived is False
```

(These rely on the existing `_ctx(ticker, realized_pct, as_of)` helper already in
`tests/test_edge_runner.py`, which builds an EventContext with an ATM call/put straddle
and a realized move. Confirm that helper sets `atm_call`/`atm_put` so the sell-vol P&L is
computable; it does in the existing runner tests.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_edge_runner.py -k "short_vol_survives or losing_directional" -v`
Expected: the short_vol survival test FAILS (current rule keys off `beat_implied_rate`,
which is None for a non-directional strategy → never survives).

- [ ] **Step 3: Implement**

In `src/prescient/edge/runner.py`:

Update the constant + comment:

```python
_SURVIVAL_MARGIN_PCT = 2.0  # must beat best baseline AVERAGE return by >= 2 points
```

Replace the `best_baseline_rate` computation and the survival condition. The current
block computes `best_baseline_rate` from `beat_implied_rate`; change it to average
return, and change the per-strategy condition to compare average return:

```python
    best_baseline_return = max(
        (
            raw[name].average_option_return_pct or 0.0
            for name in _BASELINE_SOURCES
            if name in raw
        ),
        default=0.0,
    )

    finalized: dict[str, StrategyScorecard] = {}
    for source, card in raw.items():
        if source in _BASELINE_SOURCES:
            finalized[source] = card.model_copy(update={"survived": None})
            continue
        avg_return = card.average_option_return_pct
        survived = (
            both_baselines_present
            and card.sample_size_verdict != SampleSizeVerdict.TOO_FEW
            and avg_return is not None
            and avg_return > 0.0
            and avg_return >= best_baseline_return + _SURVIVAL_MARGIN_PCT
        )
        notes = list(card.notes)
        if not both_baselines_present:
            notes.append(
                "Cannot determine survival: both coin_flip and always_up "
                "baselines are required."
            )
        elif not survived:
            notes.append(
                "Did not clearly beat baselines on average return - not tradeable."
            )
        finalized[source] = card.model_copy(
            update={"survived": survived, "notes": notes}
        )

    return EdgeBacktestResult(scorecards=finalized)
```

(Remove the now-unused `best_baseline_rate`/`rate` variables. `beat_implied_rate` remains
a reported diagnostic on the scorecard; it's just no longer the survival axis.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_edge_runner.py -v`
Expected: PASS (all existing runner tests still pass + 2 new). NOTE: if an existing
runner test asserted survival via the old beat-implied margin and now its numbers don't
clear the RETURN margin, that's a legitimate test update — adjust ONLY that assertion to
reflect the average-return rule, and STOP to report it (do not weaken the rule).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/runner.py tests/test_edge_runner.py
git add src/prescient/edge/runner.py tests/test_edge_runner.py
git commit -m "feat(edge): generalize survival to average-return axis (works for short-vol)"
```

---

### Task 6: Add ShortVolStrategy to the live script + full-suite gate

**Files:**
- Modify: `scripts/run_edge_backtest.py`
- Test: none (live script; verified by import/parse) + full-suite green.

- [ ] **Step 1: Add the strategy to the import + the strategy list**

In `scripts/run_edge_backtest.py`, update the strategy import:

```python
from prescient.edge.strategy import (
    AlwaysUpStrategy,
    CoinFlipStrategy,
    ReactionAwarePeerStrategy,
    ShortVolStrategy,
)
```

And add `ShortVolStrategy()` to the `strategies=[...]` list passed to `run_edge_backtest`:

```python
    backtest = run_edge_backtest(
        contexts=result.event_contexts,
        strategies=[
            ReactionAwarePeerStrategy(),
            ShortVolStrategy(),
            CoinFlipStrategy(),
            AlwaysUpStrategy(),
        ],
    )
```

- [ ] **Step 2: Verify parse + import + --help**

Run: `uv run python -c "import ast; ast.parse(open('scripts/run_edge_backtest.py').read()); print('parses ok')"`
Run: `uv run python -c "import importlib.util; s=importlib.util.spec_from_file_location('r','scripts/run_edge_backtest.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('imports ok')"`
Run: `uv run python scripts/run_edge_backtest.py --help`
Expected: `parses ok`, `imports ok`, argparse help.

- [ ] **Step 3: Full suite + lint**

Run: `uv run pytest -q`
Expected: all pass (existing + new edge tests).
Run: `uv run ruff check src/prescient/edge scripts/run_edge_backtest.py tests`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_edge_backtest.py
git commit -m "feat(edge): include ShortVolStrategy in the live backtest scorecard"
```

---

## Self-Review

**1. Spec coverage:**
- Capped-short P&L with inverse wing-cost + `-W` floor + return-on-W → Task 1. ✓
- `Prediction.sell_straddle` + `EventScore.stayed_within_implied` → Task 2. ✓
- `ShortVolStrategy` (NONE direction, sell_straddle) → Task 3. ✓
- Scorer sell-vol branch + `stayed_within_implied` + no directional regression → Task 4. ✓
- Runner survival generalized to average-return axis + regression guard → Task 5. ✓
- ShortVol in live script → Task 6. ✓
- Honesty haircut (no free protection) → Task 1 (wing_cost scales inversely with W,
  clamped <= credit) + test `test_capped_short_tighter_W_costs_more_wings`. ✓
- Skip-not-guess (no straddle → not_evaluable; invalid → None) → Task 1 (None) + scorer
  reuses existing missing_implied_move/missing_realized_move guards (unchanged). ✓
- Propose-only / no scoring-core rewrite of unrelated parts → only additive edits. ✓
- Retail-version interpretation → documented in spec; the model docstring (Task 1) states
  "RETAIL, UNHEDGED" explicitly. ✓

**2. Placeholder scan:** No TBD/TODO; every code step is complete with real code. The
`W` default (5.0) and wing-cost formula are concrete (locked in the plan).

**3. Type consistency:**
- `simulate_capped_short_straddle_pnl(*, straddle_price, strike, underlying_price,
  post_report_close, risk_width, cost_haircut_pct) -> OptionPnl | None` consistent across
  Task 1 (def) and Task 4 (scorer call). The scorer passes `straddle_price=
  implied.straddle_price`, `strike=context.atm_call.strike`, `underlying_price=
  context.underlying_price`, `post_report_close=realized.post_report_close`,
  `risk_width=_DEFAULT_RISK_WIDTH_W`, `cost_haircut_pct=_COST_HAIRCUT_PCT`. ✓
- `Prediction.sell_straddle` (Task 2) read by scorer (Task 4) and set by ShortVolStrategy
  (Task 3). ✓
- `EventScore.stayed_within_implied` (Task 2) set by scorer (Task 4), tested (Task 4). ✓
- Runner uses `average_option_return_pct` (exists on StrategyScorecard) — Task 5. ✓
- `ShortVolStrategy.source == "short_vol"` consistent across Tasks 3, 5, 6. ✓

## Notes / deferred

- `W` parameter sweep, full 4-strike iron condor, delta-hedged version, and forward
  paper-trading are explicitly deferred (per spec).
- The wing-cost formula is a deliberately simple monotonic approximation enforcing "no
  free protection" — not a Black-Scholes wing price. If short-vol shows promise, a more
  faithful wing model is a follow-up (flagged, not silently assumed exact).
