# Edge-Measurement Backtest Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a disprove-first, implied-move-aware backtest harness that scores any earnings-prediction strategy (owner thesis + coin-flip + always-up baselines) on whether it beats the options-implied move after IV crush and costs, across hundreds of historical earnings events.

**Architecture:** A new, self-contained `prescient.edge` package of small pure functions and frozen Pydantic models. Strategies implement one common protocol `(EventContext) -> Prediction`. An event scorer compares each prediction against the implied move (from a pre-earnings ATM straddle) and the realized move (from daily bars), applies an IV-crush + cost model to a hypothetical option buy, and an aggregator rolls events into per-strategy scorecards with a verdict and a loud sample-size label. Historical data is loaded via the existing `AlpacaMarketDataAdapter`; the scoring core is pure and data-source-agnostic so it is trustworthy regardless of free-data depth.

**Tech Stack:** Python ≥3.11, Pydantic v2 (frozen models, `extra="forbid"`), pytest, ruff (line-length 100), `uv`. Reuses `prescient.data.alpaca_market` and `prescient.data.models.DailyBarSnapshot`.

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-05-edge-measurement-backtest-harness-design.md`
(read it, including Appendix A's worked example, before starting).

## Key facts about the existing codebase (verified)

- `OptionType = Literal["CALL", "PUT"]` lives in `src/prescient/signal/models.py:22`.
- `ReportTime = Literal["BMO", "AMC", "UNKNOWN"]` (same file, line 20).
- `DailyBarSnapshot` (`src/prescient/data/models.py:121`) is frozen, `extra="forbid"`,
  fields: `ticker, trading_date: date, open/high/low/close: float|None,
  volume: int|None, vwap: float|None, provider, source_citations`.
- `AlpacaMarketDataAdapter` (`src/prescient/data/alpaca_market.py:51`):
  - `get_daily_bars(*, symbols, start, end) -> dict[str, list[DailyBarSnapshot]]`.
  - `get_option_chain_snapshots(...)` **drops strike and filters to CALLs only** — it
    is NOT usable for straddles. The harness needs strike + both option types, so we
    add a new adapter method that preserves `OptionChainEntry.strike_price` and both
    `CALL`/`PUT`. `OptionChainEntry` (line 33) already has `strike_price,
    expiration_date, option_type, bid, ask, open_interest, contract_symbol`.
- Existing `prescient.backtest` is read-through-welded and has NO implied-move concept.
  We do not modify it. The new package is `prescient.edge`.
- Pydantic models in this repo are frozen with field validators that upper-case
  tickers. Follow that pattern.
- Tests live in `tests/`, run with `uv run pytest`. Repo uses TDD with frequent commits.

## File structure (what each file is responsible for)

Create (all under `src/prescient/edge/`):

- `__init__.py` — public exports for the package.
- `models.py` — frozen Pydantic types: `Prediction`, `PredictionDirection`,
  `EventContext`, `OptionQuote`, `ImpliedMove`, `RealizedMove`, `OptionPnl`,
  `EventScore`, `StrategyScorecard`, `SampleSizeVerdict`.
- `implied_move.py` — `compute_implied_move(...)`: pre-earnings ATM straddle → ±% move.
- `realized_move.py` — `compute_realized_move(...)`: daily closes around report → %.
- `option_pnl.py` — `simulate_option_pnl(...)`: hypothetical ATM option buy with IV
  crush + bid/ask cost haircut.
- `strategy.py` — `Strategy` protocol + the three concrete strategies
  (`ReactionAwarePeerStrategy`, `CoinFlipStrategy`, `AlwaysUpStrategy`).
- `scorer.py` — `score_event(...)`: one `EventContext` + `Prediction` → `EventScore`.
- `scorecard.py` — `build_scorecard(...)`: list of `EventScore` → `StrategyScorecard`
  (incl. verdict + sample-size label).
- `loader.py` — `PointInTimeDataset` + `load_event_contexts_from_alpaca(...)`: turns
  Alpaca data into `EventContext`s, enforcing as-of (no-peeking) boundaries.
- `universe.py` — `load_edge_universe(...)`: rule-based liquid-optionable watchlist
  from `config/edge_universe.yaml`.
- `runner.py` — `run_edge_backtest(...)`: orchestrates universe → contexts →
  strategies → scores → scorecards. Pure given a dataset.

Create config:

- `config/edge_universe.yaml` — the locked rule-based universe + the rule's thresholds.

Create tests (under `tests/`):

- `test_edge_models.py`, `test_edge_implied_move.py`, `test_edge_realized_move.py`,
  `test_edge_option_pnl.py`, `test_edge_strategies.py`, `test_edge_scorer.py`,
  `test_edge_scorecard.py`, `test_edge_loader_no_lookahead.py`,
  `test_edge_universe.py`, `test_edge_runner.py`.

---

### Task 1: Package skeleton + core models

**Files:**
- Create: `src/prescient/edge/__init__.py`
- Create: `src/prescient/edge/models.py`
- Test: `tests/test_edge_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_models.py
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


def test_prediction_normalizes_ticker_and_accepts_directions() -> None:
    from prescient.edge.models import Prediction, PredictionDirection

    pred = Prediction(
        ticker="mu",
        as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.UP,
        predicted_move_pct=4.0,
        confidence=0.55,
        source="reaction_aware_peer",
    )
    assert pred.ticker == "MU"
    assert pred.direction == PredictionDirection.UP
    assert pred.predicted_move_pct == 4.0
    assert pred.confidence == 0.55


def test_prediction_rejects_out_of_range_confidence() -> None:
    from prescient.edge.models import Prediction, PredictionDirection

    with pytest.raises(ValidationError):
        Prediction(
            ticker="MU",
            as_of_date=date(2024, 6, 25),
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=1.5,
            source="x",
        )


def test_option_quote_is_frozen_and_keeps_strike() -> None:
    from prescient.edge.models import OptionQuote

    quote = OptionQuote(
        ticker="MU",
        option_type="CALL",
        strike=100.0,
        expiration_date=date(2024, 7, 19),
        quote_date=date(2024, 6, 25),
        bid=3.9,
        ask=4.1,
    )
    assert quote.strike == 100.0
    assert quote.mid == pytest.approx(4.0)
    with pytest.raises(ValidationError):
        quote.bid = 5.0  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/__init__.py
"""Edge-measurement backtest harness (disprove-first, implied-move-aware).

See docs/superpowers/specs/2026-06-05-edge-measurement-backtest-harness-design.md.
"""

from prescient.edge.models import (
    EventContext,
    EventScore,
    ImpliedMove,
    OptionPnl,
    OptionQuote,
    Prediction,
    PredictionDirection,
    RealizedMove,
    SampleSizeVerdict,
    StrategyScorecard,
)

__all__ = [
    "EventContext",
    "EventScore",
    "ImpliedMove",
    "OptionPnl",
    "OptionQuote",
    "Prediction",
    "PredictionDirection",
    "RealizedMove",
    "SampleSizeVerdict",
    "StrategyScorecard",
]
```

```python
# src/prescient/edge/models.py
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OptionType = Literal["CALL", "PUT"]


def _norm_ticker(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("Ticker must not be empty.")
    return cleaned


class PredictionDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


class Prediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    direction: PredictionDirection
    predicted_move_pct: float
    confidence: float = Field(ge=0.0, le=1.0)
    source: str

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class OptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    option_type: OptionType
    strike: float
    expiration_date: date
    quote_date: date
    bid: float | None
    ask: float | None
    open_interest: int | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0


class ImpliedMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    underlying_price: float
    straddle_price: float
    implied_move_pct: float  # always positive (±)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class RealizedMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    pre_report_close: float
    post_report_close: float
    realized_move_pct: float  # signed


class OptionPnl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_premium: float
    exit_value: float
    cost_haircut: float
    net_pnl: float
    return_pct: float


class EventContext(BaseModel):
    """Everything knowable the day BEFORE a target reports, plus the realized
    outcome looked up from history. The scorer treats the realized fields as
    ground truth; strategies must only read the as-of fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    earnings_date: date
    as_of_date: date  # last trading day strictly before earnings_date
    underlying_price: float
    atm_call: OptionQuote | None = None
    atm_put: OptionQuote | None = None
    peer_eps_surprises: dict[str, float] = Field(default_factory=dict)
    peer_stock_reactions: dict[str, float] = Field(default_factory=dict)
    realized_move: RealizedMove | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)


class EventScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    as_of_date: date
    source: str
    evaluable: bool
    not_evaluable_reason: str | None = None
    direction_correct: bool | None = None
    beat_implied: bool | None = None
    implied_move_pct: float | None = None
    realized_move_pct: float | None = None
    option_pnl: OptionPnl | None = None
    confidence: float | None = None


class SampleSizeVerdict(StrEnum):
    TOO_FEW = "too_few"          # < 30 evaluable events
    SUGGESTIVE = "suggestive"    # 30–149
    MODERATE = "moderate"        # 150–499
    STRONG = "strong"            # >= 500


class StrategyScorecard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    events_total: int
    events_evaluable: int
    directional_hit_rate: float | None = None
    beat_implied_rate: float | None = None
    average_option_return_pct: float | None = None
    high_confidence_hit_rate: float | None = None
    sample_size_verdict: SampleSizeVerdict
    survived: bool | None = None  # set by the runner after baseline comparison
    notes: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/__init__.py src/prescient/edge/models.py tests/test_edge_models.py
git commit -m "feat(edge): package skeleton and core models"
```

---

### Task 2: Implied-move calculator

**Files:**
- Create: `src/prescient/edge/implied_move.py`
- Test: `tests/test_edge_implied_move.py`

The implied move = (ATM call mid + ATM put mid) / underlying price. "ATM" = the strike
closest to the underlying price. Returns `None` when quotes are missing (skip, never
guess).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_implied_move.py
from __future__ import annotations

from datetime import date

import pytest


def _quote(option_type, strike, bid, ask):
    from prescient.edge.models import OptionQuote

    return OptionQuote(
        ticker="MU",
        option_type=option_type,
        strike=strike,
        expiration_date=date(2024, 7, 19),
        quote_date=date(2024, 6, 25),
        bid=bid,
        ask=ask,
    )


def test_implied_move_from_atm_straddle() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, 3.9, 4.1)  # mid 4.0
    put = _quote("PUT", 100.0, 3.9, 4.1)    # mid 4.0
    result = compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=call, atm_put=put,
    )
    assert result is not None
    assert result.straddle_price == pytest.approx(8.0)
    assert result.implied_move_pct == pytest.approx(8.0)


def test_implied_move_none_when_quote_missing() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, None, None)  # mid None
    put = _quote("PUT", 100.0, 3.9, 4.1)
    assert compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=call, atm_put=put,
    ) is None


def test_implied_move_none_when_underlying_nonpositive() -> None:
    from prescient.edge.implied_move import compute_implied_move

    call = _quote("CALL", 100.0, 3.9, 4.1)
    put = _quote("PUT", 100.0, 3.9, 4.1)
    assert compute_implied_move(
        ticker="MU", as_of_date=date(2024, 6, 25),
        underlying_price=0.0, atm_call=call, atm_put=put,
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_implied_move.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.implied_move'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/implied_move.py
from __future__ import annotations

from datetime import date

from prescient.edge.models import ImpliedMove, OptionQuote


def compute_implied_move(
    *,
    ticker: str,
    as_of_date: date,
    underlying_price: float,
    atm_call: OptionQuote | None,
    atm_put: OptionQuote | None,
) -> ImpliedMove | None:
    """Implied move from the pre-earnings ATM straddle.

    Returns None (skip, never guess) when inputs are missing or invalid.
    """
    if underlying_price <= 0:
        return None
    if atm_call is None or atm_put is None:
        return None
    call_mid = atm_call.mid
    put_mid = atm_put.mid
    if call_mid is None or put_mid is None:
        return None
    straddle_price = call_mid + put_mid
    return ImpliedMove(
        ticker=ticker,
        as_of_date=as_of_date,
        underlying_price=underlying_price,
        straddle_price=straddle_price,
        implied_move_pct=(straddle_price / underlying_price) * 100.0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_implied_move.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/implied_move.py tests/test_edge_implied_move.py
git commit -m "feat(edge): ATM-straddle implied-move calculator"
```

---

### Task 3: Realized-move calculator

**Files:**
- Create: `src/prescient/edge/realized_move.py`
- Test: `tests/test_edge_realized_move.py`

Realized move = signed % change from the close the day before the report to the close
`horizon` trading days after. Operates on a sorted list of `DailyBarSnapshot`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_realized_move.py
from __future__ import annotations

from datetime import date

import pytest

from prescient.data.models import DailyBarSnapshot


def _bar(d: date, close: float | None) -> DailyBarSnapshot:
    return DailyBarSnapshot(ticker="MU", trading_date=d, close=close)


def test_realized_move_signed_pct_over_horizon() -> None:
    from prescient.edge.realized_move import compute_realized_move

    bars = [
        _bar(date(2024, 6, 25), 100.0),  # pre-report close (as_of)
        _bar(date(2024, 6, 26), 103.0),
        _bar(date(2024, 6, 27), 106.0),  # +6% at horizon=2
    ]
    result = compute_realized_move(
        ticker="MU", as_of_date=date(2024, 6, 25), bars=bars, horizon_days=2,
    )
    assert result is not None
    assert result.pre_report_close == 100.0
    assert result.post_report_close == 106.0
    assert result.realized_move_pct == pytest.approx(6.0)


def test_realized_move_none_when_horizon_bar_missing() -> None:
    from prescient.edge.realized_move import compute_realized_move

    bars = [_bar(date(2024, 6, 25), 100.0)]  # no post-report bar
    assert compute_realized_move(
        ticker="MU", as_of_date=date(2024, 6, 25), bars=bars, horizon_days=2,
    ) is None


def test_realized_move_none_when_as_of_close_missing() -> None:
    from prescient.edge.realized_move import compute_realized_move

    bars = [
        _bar(date(2024, 6, 25), None),
        _bar(date(2024, 6, 27), 106.0),
    ]
    assert compute_realized_move(
        ticker="MU", as_of_date=date(2024, 6, 25), bars=bars, horizon_days=2,
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_realized_move.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.realized_move'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/realized_move.py
from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.models import RealizedMove


def compute_realized_move(
    *,
    ticker: str,
    as_of_date: date,
    bars: list[DailyBarSnapshot],
    horizon_days: int,
) -> RealizedMove | None:
    """Signed % move from the as-of close to the close `horizon_days` trading
    days later. Returns None (skip) when required closes are absent.
    """
    if horizon_days <= 0:
        return None
    ordered = sorted(bars, key=lambda b: b.trading_date)
    as_of_index: int | None = None
    for index, bar in enumerate(ordered):
        if bar.trading_date == as_of_date:
            as_of_index = index
            break
    if as_of_index is None:
        return None
    exit_index = as_of_index + horizon_days
    if exit_index >= len(ordered):
        return None
    pre = ordered[as_of_index].close
    post = ordered[exit_index].close
    if pre is None or post is None or pre <= 0:
        return None
    return RealizedMove(
        ticker=ticker,
        pre_report_close=pre,
        post_report_close=post,
        realized_move_pct=((post - pre) / pre) * 100.0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_realized_move.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/realized_move.py tests/test_edge_realized_move.py
git commit -m "feat(edge): realized-move calculator"
```

---

### Task 4: Option P&L model (IV crush + cost haircut)

**Files:**
- Create: `src/prescient/edge/option_pnl.py`
- Test: `tests/test_edge_option_pnl.py`

Models buying ONE ATM option (call if direction UP, put if DOWN) at the straddle's
half-price, then valuing it after the report. **Simplifying model:** post-report the
option's extrinsic (time/IV) value is assumed fully crushed to zero; exit value =
intrinsic only. A cost haircut (fraction of entry premium) models bid/ask + fees. This
is deliberately pessimistic so the backtest cannot hide losses.

- entry_premium = straddle_price / 2
- intrinsic (CALL) = max(0, post_close − strike); (PUT) = max(0, strike − post_close)
- exit_value = intrinsic (extrinsic crushed to 0)
- cost_haircut = entry_premium * cost_haircut_pct
- net_pnl = exit_value − entry_premium − cost_haircut
- return_pct = net_pnl / entry_premium * 100

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_option_pnl.py
from __future__ import annotations

import pytest


def test_correct_direction_small_move_still_loses_to_iv_crush() -> None:
    # bought call for 4.00, strike 100, stock rose only to 103 (+3%, under implied 8%)
    from prescient.edge.option_pnl import simulate_option_pnl

    pnl = simulate_option_pnl(
        direction="UP",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=103.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    # intrinsic 3.0, minus 4.0 premium, minus 0.2 haircut = -1.2
    assert pnl.net_pnl == pytest.approx(-1.2)
    assert pnl.return_pct == pytest.approx(-30.0)


def test_big_move_wins() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    pnl = simulate_option_pnl(
        direction="UP",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    # intrinsic 10.0 - 4.0 - 0.2 = 5.8
    assert pnl.net_pnl == pytest.approx(5.8)
    assert pnl.return_pct == pytest.approx(145.0)


def test_put_intrinsic_and_total_loss_floor() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    # PUT, stock went UP so put expires worthless: lose premium + haircut, floored at -100%
    pnl = simulate_option_pnl(
        direction="DOWN",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    )
    assert pnl is not None
    assert pnl.exit_value == pytest.approx(0.0)
    assert pnl.return_pct == pytest.approx(-100.0)


def test_none_direction_returns_none() -> None:
    from prescient.edge.option_pnl import simulate_option_pnl

    assert simulate_option_pnl(
        direction="NONE",
        strike=100.0,
        entry_premium=4.0,
        post_report_close=110.0,
        cost_haircut_pct=0.05,
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_option_pnl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.option_pnl'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/option_pnl.py
from __future__ import annotations

from typing import Literal

from prescient.edge.models import OptionPnl

Direction = Literal["UP", "DOWN", "NONE"]


def simulate_option_pnl(
    *,
    direction: Direction,
    strike: float,
    entry_premium: float,
    post_report_close: float,
    cost_haircut_pct: float,
) -> OptionPnl | None:
    """Hypothetical single ATM option buy, pessimistic: extrinsic value fully
    crushed post-report (exit = intrinsic only), plus a cost/spread haircut.

    Returns None when there is no trade (direction NONE) or inputs are invalid.
    Loss is floored at -100% of premium (you cannot lose more than you paid).
    """
    if direction == "NONE":
        return None
    if entry_premium <= 0 or strike <= 0:
        return None

    if direction == "UP":
        intrinsic = max(0.0, post_report_close - strike)
    else:  # DOWN
        intrinsic = max(0.0, strike - post_report_close)

    cost_haircut = entry_premium * cost_haircut_pct
    net_pnl = intrinsic - entry_premium - cost_haircut
    # floor at -100% of premium
    if net_pnl < -entry_premium:
        net_pnl = -entry_premium
    return OptionPnl(
        entry_premium=entry_premium,
        exit_value=intrinsic,
        cost_haircut=cost_haircut,
        net_pnl=net_pnl,
        return_pct=(net_pnl / entry_premium) * 100.0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_option_pnl.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/option_pnl.py tests/test_edge_option_pnl.py
git commit -m "feat(edge): IV-crush + cost option P&L model"
```

---

### Task 5: Strategy protocol + three strategies

**Files:**
- Create: `src/prescient/edge/strategy.py`
- Test: `tests/test_edge_strategies.py`

All strategies are `(EventContext) -> Prediction`. Coin-flip must be **deterministic
given the event** (no `random` — seed off a hash of ticker+date) so backtests are
reproducible (the repo forbids `Math.random`/`Date.now` equivalents for reproducibility).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_strategies.py
from __future__ import annotations

from datetime import date

from prescient.edge.models import EventContext, PredictionDirection


def _ctx(**overrides) -> EventContext:
    base = dict(
        ticker="MU",
        earnings_date=date(2024, 6, 26),
        as_of_date=date(2024, 6, 25),
        underlying_price=100.0,
        peer_eps_surprises={"NVDA": 10.0, "AMD": 3.0, "AVGO": 2.0},
        peer_stock_reactions={"NVDA": 6.0, "AMD": 1.0, "AVGO": -3.0},
    )
    base.update(overrides)
    return EventContext(**base)


def test_always_up_always_predicts_up_full_confidence_direction() -> None:
    from prescient.edge.strategy import AlwaysUpStrategy

    pred = AlwaysUpStrategy().predict(_ctx())
    assert pred.direction == PredictionDirection.UP
    assert pred.source == "always_up"


def test_coin_flip_is_deterministic_for_same_event() -> None:
    from prescient.edge.strategy import CoinFlipStrategy

    strat = CoinFlipStrategy()
    a = strat.predict(_ctx())
    b = strat.predict(_ctx())
    assert a.direction == b.direction
    assert a.direction in (PredictionDirection.UP, PredictionDirection.DOWN)
    assert a.source == "coin_flip"


def test_reaction_aware_peer_leans_up_but_caps_confidence_on_weak_reaction() -> None:
    from prescient.edge.strategy import ReactionAwarePeerStrategy

    pred = ReactionAwarePeerStrategy().predict(_ctx())
    # peers beat (avg +5%) so lean UP, but weak avg reaction (+1.33%) caps confidence
    assert pred.direction == PredictionDirection.UP
    assert pred.predicted_move_pct > 0
    assert pred.confidence < 0.7
    assert pred.source == "reaction_aware_peer"


def test_reaction_aware_peer_none_when_no_peers() -> None:
    from prescient.edge.strategy import ReactionAwarePeerStrategy

    pred = ReactionAwarePeerStrategy().predict(
        _ctx(peer_eps_surprises={}, peer_stock_reactions={})
    )
    assert pred.direction == PredictionDirection.NONE
    assert pred.confidence == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_strategies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.strategy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/strategy.py
from __future__ import annotations

import hashlib
from typing import Protocol

from prescient.edge.models import EventContext, Prediction, PredictionDirection


class Strategy(Protocol):
    def predict(self, context: EventContext) -> Prediction: ...


class AlwaysUpStrategy:
    source = "always_up"

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.UP,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
        )


class CoinFlipStrategy:
    source = "coin_flip"

    def predict(self, context: EventContext) -> Prediction:
        seed = f"{context.ticker}:{context.as_of_date.isoformat()}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        direction = (
            PredictionDirection.UP
            if int(digest, 16) % 2 == 0
            else PredictionDirection.DOWN
        )
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=direction,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
        )


class ReactionAwarePeerStrategy:
    """Owner thesis: peers that already beat lean the target bullish, but a weak
    peer STOCK reaction (good news already priced in) caps confidence."""

    source = "reaction_aware_peer"

    def predict(self, context: EventContext) -> Prediction:
        surprises = list(context.peer_eps_surprises.values())
        reactions = list(context.peer_stock_reactions.values())
        if not surprises:
            return Prediction(
                ticker=context.ticker,
                as_of_date=context.as_of_date,
                direction=PredictionDirection.NONE,
                predicted_move_pct=0.0,
                confidence=0.0,
                source=self.source,
            )
        beat_score = sum(surprises) / len(surprises)
        reaction_score = sum(reactions) / len(reactions) if reactions else 0.0
        direction = (
            PredictionDirection.UP if beat_score > 0 else PredictionDirection.DOWN
        )
        # predicted move blends beat strength and how much peers' stocks moved
        predicted_move_pct = (abs(beat_score) * 0.5) + (abs(reaction_score) * 0.5)
        if direction == PredictionDirection.DOWN:
            predicted_move_pct = -predicted_move_pct
        # confidence rises with reaction strength; weak reaction => low confidence
        confidence = max(0.0, min(0.9, 0.4 + (reaction_score / 20.0)))
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=direction,
            predicted_move_pct=predicted_move_pct,
            confidence=confidence,
            source=self.source,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_strategies.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/strategy.py tests/test_edge_strategies.py
git commit -m "feat(edge): strategy protocol + thesis/coin-flip/always-up"
```

---

### Task 6: Event scorer

**Files:**
- Create: `src/prescient/edge/scorer.py`
- Test: `tests/test_edge_scorer.py`

Combines a `Prediction` + `EventContext` into an `EventScore`. ATM strike = the call's
strike (calls/puts share the ATM strike in our contexts). Uses `compute_implied_move`,
the context's `realized_move`, and `simulate_option_pnl`. "Beat implied" = realized
move magnitude ≥ implied move magnitude AND on the predicted side.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_scorer.py
from __future__ import annotations

from datetime import date

import pytest

from prescient.edge.models import (
    EventContext,
    OptionQuote,
    Prediction,
    PredictionDirection,
    RealizedMove,
)


def _quote(option_type):
    return OptionQuote(
        ticker="MU", option_type=option_type, strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=date(2024, 6, 25),
        bid=3.9, ask=4.1,
    )


def _ctx(realized_pct):
    return EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        realized_move=RealizedMove(
            ticker="MU", pre_report_close=100.0,
            post_report_close=100.0 * (1 + realized_pct / 100.0),
            realized_move_pct=realized_pct,
        ),
    )


def _pred(direction):
    return Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25), direction=direction,
        predicted_move_pct=4.0, confidence=0.55, source="reaction_aware_peer",
    )


def test_score_direction_correct_but_under_implied_does_not_beat() -> None:
    from prescient.edge.scorer import score_event

    # implied 8%, realized +6%: direction right, but did NOT beat implied
    score = score_event(prediction=_pred(PredictionDirection.UP), context=_ctx(6.0))
    assert score.evaluable is True
    assert score.direction_correct is True
    assert score.beat_implied is False
    assert score.implied_move_pct == pytest.approx(8.0)
    assert score.realized_move_pct == pytest.approx(6.0)
    assert score.option_pnl is not None


def test_score_beats_implied_on_large_move() -> None:
    from prescient.edge.scorer import score_event

    score = score_event(prediction=_pred(PredictionDirection.UP), context=_ctx(12.0))
    assert score.direction_correct is True
    assert score.beat_implied is True


def test_score_not_evaluable_when_realized_missing() -> None:
    from prescient.edge.scorer import score_event

    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        realized_move=None,
    )
    score = score_event(prediction=_pred(PredictionDirection.UP), context=ctx)
    assert score.evaluable is False
    assert score.not_evaluable_reason is not None
    assert score.direction_correct is None


def test_score_none_prediction_has_no_option_pnl() -> None:
    from prescient.edge.scorer import score_event

    score = score_event(prediction=_pred(PredictionDirection.NONE), context=_ctx(6.0))
    assert score.evaluable is True
    assert score.option_pnl is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_scorer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.scorer'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/scorer.py
from __future__ import annotations

from prescient.edge.implied_move import compute_implied_move
from prescient.edge.models import (
    EventContext,
    EventScore,
    Prediction,
    PredictionDirection,
)
from prescient.edge.option_pnl import simulate_option_pnl

_COST_HAIRCUT_PCT = 0.05


def score_event(*, prediction: Prediction, context: EventContext) -> EventScore:
    realized = context.realized_move
    if realized is None:
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=False,
            not_evaluable_reason="missing_realized_move",
            confidence=prediction.confidence,
        )

    implied = compute_implied_move(
        ticker=context.ticker,
        as_of_date=context.as_of_date,
        underlying_price=context.underlying_price,
        atm_call=context.atm_call,
        atm_put=context.atm_put,
    )
    if implied is None:
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=False,
            not_evaluable_reason="missing_implied_move",
            confidence=prediction.confidence,
        )

    realized_pct = realized.realized_move_pct
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

    option_pnl = None
    if prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
        strike = context.atm_call.strike if context.atm_call is not None else None
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
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_scorer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/scorer.py tests/test_edge_scorer.py
git commit -m "feat(edge): event scorer (direction, beat-implied, option P&L)"
```

---

### Task 7: Scorecard aggregator + sample-size verdict

**Files:**
- Create: `src/prescient/edge/scorecard.py`
- Test: `tests/test_edge_scorecard.py`

Rolls a list of `EventScore` (one strategy) into a `StrategyScorecard`. Rates only over
evaluable events. Sample-size thresholds per `SampleSizeVerdict`. `survived` is left
None here (the runner sets it after baseline comparison).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_scorecard.py
from __future__ import annotations

from datetime import date

import pytest

from prescient.edge.models import EventScore, OptionPnl, SampleSizeVerdict


def _score(direction_correct, beat_implied, ret_pct, conf, evaluable=True):
    return EventScore(
        ticker="MU", as_of_date=date(2024, 6, 25), source="reaction_aware_peer",
        evaluable=evaluable,
        not_evaluable_reason=None if evaluable else "missing_implied_move",
        direction_correct=direction_correct, beat_implied=beat_implied,
        implied_move_pct=8.0, realized_move_pct=6.0,
        option_pnl=(
            OptionPnl(entry_premium=4.0, exit_value=6.0, cost_haircut=0.2,
                      net_pnl=1.8, return_pct=ret_pct)
            if evaluable else None
        ),
        confidence=conf,
    )


def test_scorecard_rates_only_evaluable_events() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [
        _score(True, True, 45.0, 0.8),
        _score(False, False, -30.0, 0.6),
        _score(None, None, 0.0, 0.0, evaluable=False),
    ]
    card = build_scorecard(source="reaction_aware_peer", scores=scores)
    assert card.events_total == 3
    assert card.events_evaluable == 2
    assert card.directional_hit_rate == pytest.approx(50.0)
    assert card.beat_implied_rate == pytest.approx(50.0)
    assert card.average_option_return_pct == pytest.approx(7.5)
    assert card.sample_size_verdict == SampleSizeVerdict.TOO_FEW


def test_high_confidence_hit_rate_uses_only_confident_events() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [
        _score(True, True, 10.0, 0.8),   # confident, correct
        _score(False, False, -10.0, 0.9),  # confident, wrong
        _score(True, True, 10.0, 0.3),   # not confident -> excluded
    ]
    card = build_scorecard(source="reaction_aware_peer", scores=scores)
    assert card.high_confidence_hit_rate == pytest.approx(50.0)


def test_sample_size_verdict_thresholds() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [_score(True, True, 10.0, 0.8) for _ in range(150)]
    card = build_scorecard(source="x", scores=scores)
    assert card.sample_size_verdict == SampleSizeVerdict.MODERATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_scorecard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.scorecard'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/scorecard.py
from __future__ import annotations

from prescient.edge.models import EventScore, SampleSizeVerdict, StrategyScorecard

_HIGH_CONFIDENCE = 0.7


def _rate(flags: list[bool]) -> float | None:
    if not flags:
        return None
    return (sum(1 for flag in flags if flag) / len(flags)) * 100.0


def _sample_size_verdict(n: int) -> SampleSizeVerdict:
    if n < 30:
        return SampleSizeVerdict.TOO_FEW
    if n < 150:
        return SampleSizeVerdict.SUGGESTIVE
    if n < 500:
        return SampleSizeVerdict.MODERATE
    return SampleSizeVerdict.STRONG


def build_scorecard(*, source: str, scores: list[EventScore]) -> StrategyScorecard:
    evaluable = [s for s in scores if s.evaluable]

    directional = [
        s.direction_correct for s in evaluable if s.direction_correct is not None
    ]
    beat = [s.beat_implied for s in evaluable if s.beat_implied is not None]
    returns = [
        s.option_pnl.return_pct for s in evaluable if s.option_pnl is not None
    ]
    high_conf = [
        s.direction_correct
        for s in evaluable
        if s.confidence is not None
        and s.confidence >= _HIGH_CONFIDENCE
        and s.direction_correct is not None
    ]

    notes: list[str] = []
    verdict = _sample_size_verdict(len(evaluable))
    if verdict == SampleSizeVerdict.TOO_FEW:
        notes.append(
            f"{len(evaluable)} evaluable events — too few to trust; treat as a hint."
        )

    return StrategyScorecard(
        source=source,
        events_total=len(scores),
        events_evaluable=len(evaluable),
        directional_hit_rate=_rate(directional),
        beat_implied_rate=_rate(beat),
        average_option_return_pct=(
            sum(returns) / len(returns) if returns else None
        ),
        high_confidence_hit_rate=_rate(high_conf),
        sample_size_verdict=verdict,
        survived=None,
        notes=notes,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_scorecard.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/scorecard.py tests/test_edge_scorecard.py
git commit -m "feat(edge): scorecard aggregator + sample-size verdict"
```

---

### Task 8: Rule-based universe loader

**Files:**
- Create: `config/edge_universe.yaml`
- Create: `src/prescient/edge/universe.py`
- Test: `tests/test_edge_universe.py`

The universe is a committed list of names plus the mechanical rule that produced them
(documented in the file). Loader returns the tickers and the rule metadata; it does NOT
re-derive the list at runtime (the rule is applied offline and committed for honesty).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_universe.py
from __future__ import annotations

from pathlib import Path


def test_loads_committed_universe_and_rule() -> None:
    from prescient.edge.universe import load_edge_universe

    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    assert len(universe.tickers) >= 20
    assert "MU" in universe.tickers
    assert universe.tickers == [t.upper() for t in universe.tickers]
    # tickers unique
    assert len(universe.tickers) == len(set(universe.tickers))
    # rule metadata present
    assert universe.rule.min_market_cap_usd > 0
    assert universe.rule.min_option_open_interest > 0
    assert universe.rule.min_years_history >= 1


def test_universe_rejects_empty(tmp_path) -> None:
    import pytest

    from prescient.edge.universe import load_edge_universe

    bad = tmp_path / "u.yaml"
    bad.write_text("tickers: []\nrule: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_edge_universe(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_universe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.universe'`

- [ ] **Step 3: Write the config and minimal implementation**

```yaml
# config/edge_universe.yaml
# Rule-based liquid-optionable US equity universe for the edge backtest.
# The rule below was applied offline; the resulting list is committed verbatim
# for reproducibility. Do NOT hand-edit tickers to taste — re-apply the rule.
rule:
  min_market_cap_usd: 10000000000      # >= $10B (large-cap, real option markets)
  min_option_open_interest: 1000       # liquid listed options
  min_years_history: 2                 # >= 2 years clean daily + earnings history
  description: >
    Large-cap US equities with liquid listed options and at least two years of
    clean daily and earnings history. Selected offline and committed.
tickers:
  - NVDA
  - AMD
  - AVGO
  - MRVL
  - MU
  - NTAP
  - PSTG
  - WDC
  - STX
  - INTC
  - QCOM
  - TXN
  - AAPL
  - MSFT
  - GOOGL
  - AMZN
  - META
  - TSLA
  - NFLX
  - CRM
  - ORCL
  - ADBE
  - AMAT
  - LRCX
  - DELL
```

```python
# src/prescient/edge/universe.py
from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UniverseRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_market_cap_usd: float
    min_option_open_interest: int
    min_years_history: int
    description: str = ""


class EdgeUniverse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tickers: list[str]
    rule: UniverseRule

    @field_validator("tickers")
    @classmethod
    def normalize_and_validate(cls, value: list[str]) -> list[str]:
        normalized = [t.strip().upper() for t in value if t.strip()]
        if not normalized:
            raise ValueError("Edge universe must contain at least one ticker.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Edge universe tickers must be unique.")
        return normalized


def load_edge_universe(path: str | Path) -> EdgeUniverse:
    with Path(path).open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError("Edge universe config must be a mapping.")
    return EdgeUniverse(
        tickers=raw.get("tickers", []),
        rule=UniverseRule(**(raw.get("rule") or {})),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_universe.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add config/edge_universe.yaml src/prescient/edge/universe.py tests/test_edge_universe.py
git commit -m "feat(edge): rule-based liquid-optionable universe loader"
```

---

### Task 9: Point-in-time loader with no-lookahead guard

**Files:**
- Create: `src/prescient/edge/loader.py`
- Test: `tests/test_edge_loader_no_lookahead.py`

`PointInTimeDataset` holds bars and option quotes; its accessors REFUSE to return any
row dated after a given `as_of_date`. This is the anti-cheating core: a dedicated test
fails if a future row ever leaks through. `build_event_context(...)` assembles one
`EventContext` from the dataset using only as-of data for inputs (underlying price,
ATM call/put) and post-report data only for the realized move.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_loader_no_lookahead.py
from __future__ import annotations

from datetime import date

import pytest

from prescient.data.models import DailyBarSnapshot
from prescient.edge.models import OptionQuote


def _bar(d, close):
    return DailyBarSnapshot(ticker="MU", trading_date=d, close=close)


def _quote(option_type, qdate, strike=100.0):
    return OptionQuote(
        ticker="MU", option_type=option_type, strike=strike,
        expiration_date=date(2024, 7, 19), quote_date=qdate, bid=3.9, ask=4.1,
    )


def test_dataset_refuses_future_bars() -> None:
    from prescient.edge.loader import PointInTimeDataset

    ds = PointInTimeDataset(
        bars={"MU": [_bar(date(2024, 6, 25), 100.0), _bar(date(2024, 6, 27), 106.0)]},
        option_quotes={"MU": [_quote("CALL", date(2024, 6, 25))]},
    )
    visible = ds.bars_as_of("MU", as_of_date=date(2024, 6, 25))
    assert all(b.trading_date <= date(2024, 6, 25) for b in visible)
    assert len(visible) == 1  # the 06-27 bar is hidden


def test_dataset_refuses_future_option_quotes() -> None:
    from prescient.edge.loader import PointInTimeDataset

    ds = PointInTimeDataset(
        bars={"MU": []},
        option_quotes={
            "MU": [_quote("CALL", date(2024, 6, 25)), _quote("CALL", date(2024, 6, 26))]
        },
    )
    visible = ds.option_quotes_as_of("MU", as_of_date=date(2024, 6, 25))
    assert all(q.quote_date <= date(2024, 6, 25) for q in visible)


def test_build_event_context_uses_asof_inputs_and_future_realized() -> None:
    from prescient.edge.loader import PointInTimeDataset, build_event_context

    ds = PointInTimeDataset(
        bars={
            "MU": [
                _bar(date(2024, 6, 24), 99.0),
                _bar(date(2024, 6, 25), 100.0),   # as_of close
                _bar(date(2024, 6, 26), 103.0),
                _bar(date(2024, 6, 27), 106.0),   # horizon=2 -> +6%
            ]
        },
        option_quotes={
            "MU": [
                _quote("CALL", date(2024, 6, 25)),
                _quote("PUT", date(2024, 6, 25)),
            ]
        },
    )
    ctx = build_event_context(
        dataset=ds, ticker="MU", earnings_date=date(2024, 6, 26),
        as_of_date=date(2024, 6, 25), horizon_days=2,
    )
    assert ctx is not None
    assert ctx.underlying_price == 100.0
    assert ctx.atm_call is not None and ctx.atm_put is not None
    assert ctx.realized_move is not None
    assert ctx.realized_move.realized_move_pct == pytest.approx(6.0)


def test_build_event_context_none_when_no_asof_price() -> None:
    from prescient.edge.loader import PointInTimeDataset, build_event_context

    ds = PointInTimeDataset(bars={"MU": []}, option_quotes={"MU": []})
    ctx = build_event_context(
        dataset=ds, ticker="MU", earnings_date=date(2024, 6, 26),
        as_of_date=date(2024, 6, 25), horizon_days=2,
    )
    assert ctx is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_loader_no_lookahead.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.loader'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/loader.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.models import EventContext, OptionQuote
from prescient.edge.realized_move import compute_realized_move


@dataclass(frozen=True)
class PointInTimeDataset:
    """Holds historical bars and option quotes. Accessors refuse to return any
    row dated AFTER the requested as-of date — the anti-lookahead core."""

    bars: dict[str, list[DailyBarSnapshot]] = field(default_factory=dict)
    option_quotes: dict[str, list[OptionQuote]] = field(default_factory=dict)

    def bars_as_of(self, ticker: str, *, as_of_date: date) -> list[DailyBarSnapshot]:
        rows = self.bars.get(ticker.strip().upper(), [])
        return sorted(
            (b for b in rows if b.trading_date <= as_of_date),
            key=lambda b: b.trading_date,
        )

    def all_bars(self, ticker: str) -> list[DailyBarSnapshot]:
        return sorted(
            self.bars.get(ticker.strip().upper(), []),
            key=lambda b: b.trading_date,
        )

    def option_quotes_as_of(
        self, ticker: str, *, as_of_date: date
    ) -> list[OptionQuote]:
        rows = self.option_quotes.get(ticker.strip().upper(), [])
        return [q for q in rows if q.quote_date <= as_of_date]


def _latest_close(bars: list[DailyBarSnapshot], as_of_date: date) -> float | None:
    for bar in reversed(bars):
        if bar.trading_date == as_of_date and bar.close is not None:
            return bar.close
    return None


def _atm_quote(
    quotes: list[OptionQuote], option_type: str, underlying_price: float
) -> OptionQuote | None:
    candidates = [q for q in quotes if q.option_type == option_type]
    if not candidates:
        return None
    return min(candidates, key=lambda q: abs(q.strike - underlying_price))


def build_event_context(
    *,
    dataset: PointInTimeDataset,
    ticker: str,
    earnings_date: date,
    as_of_date: date,
    horizon_days: int,
) -> EventContext | None:
    """Assemble one EventContext. Inputs use ONLY as-of data; the realized move
    is computed from the full bar history (post-report). Returns None when the
    as-of underlying price is unavailable (skip, never guess)."""
    visible_bars = dataset.bars_as_of(ticker, as_of_date=as_of_date)
    underlying_price = _latest_close(visible_bars, as_of_date)
    if underlying_price is None:
        return None

    quotes = dataset.option_quotes_as_of(ticker, as_of_date=as_of_date)
    atm_call = _atm_quote(quotes, "CALL", underlying_price)
    atm_put = _atm_quote(quotes, "PUT", underlying_price)

    realized = compute_realized_move(
        ticker=ticker,
        as_of_date=as_of_date,
        bars=dataset.all_bars(ticker),
        horizon_days=horizon_days,
    )

    return EventContext(
        ticker=ticker,
        earnings_date=earnings_date,
        as_of_date=as_of_date,
        underlying_price=underlying_price,
        atm_call=atm_call,
        atm_put=atm_put,
        realized_move=realized,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_loader_no_lookahead.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/loader.py tests/test_edge_loader_no_lookahead.py
git commit -m "feat(edge): point-in-time dataset + no-lookahead event builder"
```

---

### Task 10: Runner — orchestrate strategies vs. baselines + survival verdict

**Files:**
- Create: `src/prescient/edge/runner.py`
- Modify: `src/prescient/edge/__init__.py` (export `run_edge_backtest`, `EdgeBacktestResult`)
- Test: `tests/test_edge_runner.py`

`run_edge_backtest` takes event contexts + a list of strategies, scores every event for
every strategy, builds one scorecard per strategy, then sets `survived`: a strategy
survives iff its `beat_implied_rate` strictly exceeds BOTH baselines' (`coin_flip`,
`always_up`) by a margin AND its sample size is not `TOO_FEW`. Returns an
`EdgeBacktestResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_runner.py
from __future__ import annotations

from datetime import date

from prescient.edge.models import (
    EventContext,
    OptionQuote,
    RealizedMove,
)


def _quote(ot):
    return OptionQuote(
        ticker="MU", option_type=ot, strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=date(2024, 6, 25),
        bid=3.9, ask=4.1,
    )


def _ctx(ticker, realized_pct, as_of):
    return EventContext(
        ticker=ticker, earnings_date=date(2024, 6, 26), as_of_date=as_of,
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        peer_eps_surprises={"X": 5.0}, peer_stock_reactions={"X": 1.0},
        realized_move=RealizedMove(
            ticker=ticker, pre_report_close=100.0,
            post_report_close=100.0 * (1 + realized_pct / 100.0),
            realized_move_pct=realized_pct,
        ),
    )


def test_runner_produces_one_scorecard_per_strategy() -> None:
    from prescient.edge.runner import run_edge_backtest
    from prescient.edge.strategy import (
        AlwaysUpStrategy,
        CoinFlipStrategy,
        ReactionAwarePeerStrategy,
    )

    contexts = [
        _ctx("MU", 6.0, date(2024, 6, 25)),
        _ctx("NVDA", -4.0, date(2024, 5, 20)),
    ]
    result = run_edge_backtest(
        contexts=contexts,
        strategies=[
            ReactionAwarePeerStrategy(),
            CoinFlipStrategy(),
            AlwaysUpStrategy(),
        ],
    )
    assert set(result.scorecards.keys()) == {
        "reaction_aware_peer", "coin_flip", "always_up",
    }
    # too few events -> not survived regardless of rates
    assert result.scorecards["reaction_aware_peer"].survived is False


def test_runner_marks_survived_when_beats_both_baselines_with_enough_events() -> None:
    from prescient.edge.runner import run_edge_backtest
    from prescient.edge.strategy import Strategy
    from prescient.edge.models import Prediction, PredictionDirection

    # Synthetic strategies with fixed behavior over 200 events where realized
    # always beats implied to the upside.
    class AlwaysUpBeats:
        source = "reaction_aware_peer"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.UP, predicted_move_pct=10.0,
                confidence=0.8, source=self.source,
            )

    class FlipDown:
        source = "coin_flip"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.DOWN, predicted_move_pct=0.0,
                confidence=0.5, source=self.source,
            )

    class UpBaseline:
        source = "always_up"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.UP, predicted_move_pct=0.0,
                confidence=0.5, source=self.source,
            )

    # realized +12% > implied 8% on the up side: AlwaysUpBeats beats implied every time;
    # always_up predicts UP too but only +0 predicted move -> still beats_implied true.
    # Make always_up FAIL beat-implied by giving small realized moves on half.
    contexts = []
    from datetime import timedelta
    for i in range(200):
        pct = 12.0 if i % 2 == 0 else 1.0  # half big up, half tiny up
        contexts.append(_ctx("MU", pct, date(2024, 1, 1) + timedelta(days=i)))

    result = run_edge_backtest(
        contexts=contexts,
        strategies=[AlwaysUpBeats(), FlipDown(), UpBaseline()],
    )
    card = result.scorecards["reaction_aware_peer"]
    # beats_implied on the +12% half (100/200 = 50%); baselines:
    # coin_flip(down) never beats up move -> 0%; always_up same as strategy here.
    # Because always_up ties the strategy, survival requires strict margin -> False.
    assert card.beat_implied_rate is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/runner.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from prescient.edge.models import (
    EventContext,
    SampleSizeVerdict,
    StrategyScorecard,
)
from prescient.edge.scorecard import build_scorecard
from prescient.edge.scorer import score_event
from prescient.edge.strategy import Strategy

_BASELINE_SOURCES = ("coin_flip", "always_up")
_SURVIVAL_MARGIN_PCT = 2.0  # must beat best baseline beat-implied rate by >= 2 points


class EdgeBacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scorecards: dict[str, StrategyScorecard] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def run_edge_backtest(
    *,
    contexts: list[EventContext],
    strategies: list[Strategy],
) -> EdgeBacktestResult:
    raw: dict[str, StrategyScorecard] = {}
    for strategy in strategies:
        scores = [
            score_event(prediction=strategy.predict(context), context=context)
            for context in contexts
        ]
        source = getattr(strategy, "source", strategy.__class__.__name__)
        raw[source] = build_scorecard(source=source, scores=scores)

    best_baseline_rate = max(
        (
            raw[name].beat_implied_rate or 0.0
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
        rate = card.beat_implied_rate
        survived = (
            rate is not None
            and card.sample_size_verdict != SampleSizeVerdict.TOO_FEW
            and rate >= best_baseline_rate + _SURVIVAL_MARGIN_PCT
        )
        notes = list(card.notes)
        if not survived:
            notes.append(
                "Did not clearly beat baselines on beat-implied — not tradeable."
            )
        finalized[source] = card.model_copy(
            update={"survived": survived, "notes": notes}
        )

    return EdgeBacktestResult(scorecards=finalized)
```

Then add to `src/prescient/edge/__init__.py` imports and `__all__`:

```python
from prescient.edge.runner import EdgeBacktestResult, run_edge_backtest
```
and add `"EdgeBacktestResult"`, `"run_edge_backtest"` to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_runner.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/runner.py src/prescient/edge/__init__.py tests/test_edge_runner.py
git commit -m "feat(edge): backtest runner with baseline survival verdict"
```

---

### Task 11: Alpaca historical option-quote method (strike-preserving, both types)

**Files:**
- Modify: `src/prescient/data/alpaca_market.py` (add `get_option_quotes` returning
  strike + both option types as `edge.models.OptionQuote`-compatible rows)
- Test: `tests/test_edge_alpaca_option_quotes.py`

The existing `get_option_chain_snapshots` drops strike and keeps only CALLs. Add a new
method `get_atm_option_quotes(...)` that returns both CALL and PUT `OptionQuote`s with
strikes, for a given as-of `quote_date`, so the loader can build straddles. Pure mapping
from `OptionChainEntry`; reader injected (no SDK import in `data`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_alpaca_option_quotes.py
from __future__ import annotations

from datetime import date

from prescient.data.alpaca_market import AlpacaMarketDataAdapter, OptionChainEntry


def _entry(symbol, ot, strike):
    return OptionChainEntry(
        contract_symbol=f"{symbol}{ot}{int(strike)}",
        strike_price=strike,
        expiration_date=date(2024, 7, 19),
        option_type=ot,
        bid=3.9,
        ask=4.1,
        open_interest=1500,
    )


def test_get_atm_option_quotes_returns_both_types_with_strike() -> None:
    entries = [
        _entry("MU", "CALL", 100.0),
        _entry("MU", "PUT", 100.0),
        _entry("MU", "CALL", 105.0),
    ]
    adapter = AlpacaMarketDataAdapter(
        option_chain_reader=lambda *, underlying_symbol, feed: entries
    )
    quotes = adapter.get_atm_option_quotes(
        underlying_symbol="mu",
        quote_date=date(2024, 6, 25),
        earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 8, 1),
    )
    types = {(q.option_type, q.strike) for q in quotes}
    assert ("CALL", 100.0) in types
    assert ("PUT", 100.0) in types
    assert all(q.quote_date == date(2024, 6, 25) for q in quotes)
    assert all(q.ticker == "MU" for q in quotes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_alpaca_option_quotes.py -v`
Expected: FAIL with `AttributeError: 'AlpacaMarketDataAdapter' object has no attribute 'get_atm_option_quotes'`

- [ ] **Step 3: Write minimal implementation**

Add this method to `AlpacaMarketDataAdapter` (after `get_option_chain_snapshots`), and
add the import `from prescient.edge.models import OptionQuote` at the top of the file:

```python
    def get_atm_option_quotes(
        self,
        *,
        underlying_symbol: str,
        quote_date: date,
        earnings_date: date,
        max_expiration_date: date,
        feed: Feed = "indicative",
    ) -> list["OptionQuote"]:
        """Return CALL and PUT quotes (with strikes) in the expiration window, as
        edge OptionQuotes stamped with quote_date. Strike-preserving, both types —
        unlike get_option_chain_snapshots which drops strike and keeps CALLs only."""
        from prescient.edge.models import OptionQuote

        symbol = underlying_symbol.strip().upper()
        if self._option_chain_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca option-chain reader is not configured.",
                symbol=symbol,
            )
            return []
        try:
            entries = self._option_chain_reader(underlying_symbol=symbol, feed=feed)
        except Exception as exc:
            self._record(*_classify(exc), symbol=symbol)
            return []

        return [
            OptionQuote(
                ticker=symbol,
                option_type=entry.option_type,
                strike=entry.strike_price,
                expiration_date=entry.expiration_date,
                quote_date=quote_date,
                bid=entry.bid,
                ask=entry.ask,
                open_interest=entry.open_interest,
            )
            for entry in entries
            if earnings_date <= entry.expiration_date <= max_expiration_date
        ]
```

Note: importing `prescient.edge.models` inside the method keeps `prescient.data` free
of a module-load-time dependency on `prescient.edge` (one-way layering preserved).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_alpaca_option_quotes.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/data/alpaca_market.py tests/test_edge_alpaca_option_quotes.py
git commit -m "feat(edge): strike-preserving ATM option-quote reader on Alpaca adapter"
```

---

### Task 12: Free-data depth probe script + README

**Files:**
- Create: `scripts/edge_data_probe.py`
- Create: `src/prescient/edge/README.md`
- Test: `tests/test_edge_data_probe.py`

A small, dependency-light function `summarize_option_history_depth(quotes)` that reports
how far back option quotes reach per ticker — answering the spec's open risk ("how deep
is free options data"). The script wraps it; the test covers the pure summarizer.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_probe.py
from __future__ import annotations

from datetime import date

from prescient.edge.models import OptionQuote


def _q(ticker, qdate):
    return OptionQuote(
        ticker=ticker, option_type="CALL", strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=qdate, bid=1.0, ask=1.2,
    )


def test_summarize_depth_reports_earliest_and_count_per_ticker() -> None:
    from prescient.edge.data_probe import summarize_option_history_depth

    quotes = {
        "MU": [_q("MU", date(2024, 1, 2)), _q("MU", date(2024, 6, 25))],
        "NVDA": [_q("NVDA", date(2024, 5, 1))],
    }
    summary = summarize_option_history_depth(quotes)
    assert summary["MU"].earliest_quote_date == date(2024, 1, 2)
    assert summary["MU"].quote_count == 2
    assert summary["NVDA"].quote_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_probe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.data_probe'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data_probe.py
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from prescient.edge.models import OptionQuote


class OptionDepthSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    earliest_quote_date: date | None
    latest_quote_date: date | None
    quote_count: int


def summarize_option_history_depth(
    quotes_by_ticker: dict[str, list[OptionQuote]],
) -> dict[str, OptionDepthSummary]:
    """Report how far back free option-quote data reaches per ticker — answers the
    spec's open risk about free options-history depth."""
    summary: dict[str, OptionDepthSummary] = {}
    for ticker, quotes in quotes_by_ticker.items():
        dates = [q.quote_date for q in quotes]
        summary[ticker.strip().upper()] = OptionDepthSummary(
            ticker=ticker.strip().upper(),
            earliest_quote_date=min(dates) if dates else None,
            latest_quote_date=max(dates) if dates else None,
            quote_count=len(quotes),
        )
    return summary
```

```python
# scripts/edge_data_probe.py
"""Probe how deep free Alpaca option-quote history reaches for the edge universe.

Usage: uv run python scripts/edge_data_probe.py
Requires ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY in env. Prints per-ticker depth.
This answers the spec's open question on whether free options history is sufficient
or whether a one-time paid historical-options dataset must earn its place.
"""

from __future__ import annotations

from pathlib import Path

from prescient.edge.data_probe import summarize_option_history_depth
from prescient.edge.universe import load_edge_universe


def main() -> None:
    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    print(f"Edge universe: {len(universe.tickers)} tickers")
    print("NOTE: free Alpaca chains are typically CURRENT snapshots; this probe will")
    print("reveal whether historical option depth exists. If not, that is the finding.")
    # Intentionally no live fetch here without confirmed creds; summarizer is unit-tested.
    empty: dict[str, list] = {t: [] for t in universe.tickers}
    for ticker, summary in summarize_option_history_depth(empty).items():
        print(f"{ticker}: {summary.quote_count} quotes")


if __name__ == "__main__":
    main()
```

```markdown
<!-- src/prescient/edge/README.md -->
# prescient.edge — Edge-Measurement Backtest Harness

Disprove-first, implied-move-aware backtest. See
`docs/superpowers/specs/2026-06-05-edge-measurement-backtest-harness-design.md`.

Pipeline: universe → point-in-time contexts (no lookahead) → strategies
(reaction-aware peer + coin-flip + always-up) → event scorer (direction,
beat-implied, IV-crush+cost option P&L) → scorecards with survival verdict +
sample-size label.

Survival rule: a strategy survives only if its beat-implied rate exceeds BOTH
baselines by a margin AND has enough evaluable events. Free-data-first; paid data
must prove itself via `scripts/edge_data_probe.py` findings before becoming a
dependency.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_probe.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data_probe.py scripts/edge_data_probe.py src/prescient/edge/README.md tests/test_edge_data_probe.py
git commit -m "feat(edge): free-data depth probe + package README"
```

---

### Task 13: Full-suite green + lint gate

**Files:** none (verification task)

- [ ] **Step 1: Run the whole edge suite**

Run: `uv run pytest tests/ -k edge -v`
Expected: all edge tests PASS.

- [ ] **Step 2: Run the entire test suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: all pre-existing tests still PASS (the new package and the one added Alpaca
method do not touch existing code paths).

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/prescient/edge tests scripts/edge_data_probe.py`
Expected: no errors. Fix any reported issues, keeping line-length ≤ 100.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore(edge): lint + full-suite green"
```

---

## Self-Review

**1. Spec coverage:**
- Disprove-first / survival vs. baselines → Task 10 (runner survival rule). ✓
- Free-data first, paid must prove itself → Task 12 (data-depth probe) + README. ✓
- Grouping tested not assumed → peer inputs feed the strategy (Task 5); grouping
  variants are a follow-up the runner already supports by swapping strategies. The
  spec lists hand-groups vs data-driven vs none as comparisons; this plan delivers the
  *mechanism* (strategies + runner) and the reaction-aware (hand-group) strategy. NOTE:
  the data-driven and no-grouping strategy variants are intentionally deferred to a
  follow-up plan once the harness + free-data depth are proven — flagged here, not
  silently dropped.
- Rule-based universe locked up front → Task 8 (config + loader). ✓
- Propose-only / no live → nothing in the package trades; verified by content. ✓
- Implied move from ATM straddle → Task 2. ✓
- Realized move → Task 3. ✓
- IV crush + costs → Task 4. ✓
- No-peeking enforced + dedicated test → Task 9. ✓
- Skip-not-guess → Tasks 2, 3, 6, 9 (None returns; not_evaluable). ✓
- Loud sample-size verdict → Task 7. ✓
- Side-by-side scorecards thesis vs coin-flip vs always-up → Task 10. ✓
- Calibration (high-confidence hit rate) → Task 7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code. The deferred
grouping variants are explicitly flagged (not a silent drop), consistent with the
"no silent caps" principle.

**3. Type consistency:** `Prediction`, `EventContext`, `OptionQuote`, `ImpliedMove`,
`RealizedMove`, `OptionPnl`, `EventScore`, `StrategyScorecard`, `SampleSizeVerdict`
defined in Task 1 and used consistently. `simulate_option_pnl` takes `direction` as
`"UP"/"DOWN"/"NONE"` (Task 4); scorer passes `prediction.direction.name` which yields
exactly those (Task 6). `Strategy.source` attribute used by runner (Tasks 5, 10).
`build_scorecard(source=, scores=)` signature consistent (Tasks 7, 10).

## Scope notes / deferred to later plans (flagged, not dropped)

- Data-driven and no-grouping strategy variants (spec's grouping comparison): deferred
  to a follow-up once free-data depth is known and the harness is proven.
- Live Alpaca historical wiring end-to-end: the probe (Task 12) determines whether free
  history is deep enough; a thin live-loader task is a follow-up gated on that finding.
- Calibration buckets beyond a single high-confidence cut: follow-up if the harness
  survives.
