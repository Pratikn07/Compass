# R9.1 Peer Read-Through Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a cold-path backtest package that replays historical peer-read-through setups and measures both target-stock follow-through and strategy trade P&L before real-money risk.

**Architecture:** Add a new `prescient.backtest` package with pure Pydantic models, fixture-driven replay helpers, a deterministic runner, and a compact report summary. The package will call existing signal evaluation code with historical inputs, compute outcome metrics from explicit historical prices/quotes, and stay outside live runtime, broker, risk, and data-provider hot paths.

**Tech Stack:** Python, Pydantic v2, pytest, uv, ruff.

---

## Source PRD

Use the R9.1 PRD content from the conversation as source of truth.

Create the durable PRD file before implementation:

`/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/09-backtest-r9-1-peer-readthrough-edge-prd.md`

## File Structure

Create:

- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/__init__.py`
  - Public exports for R9.1 models and runner functions.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/models.py`
  - Backtest request, fixture data, setup result, outcome, summary, and warning models.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/runner.py`
  - Main `run_peer_readthrough_backtest(...)` orchestration.
- `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/outcomes.py`
  - Underlying follow-through and stock/option P&L calculation helpers.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r9_1_peer_readthrough_backtest.py`
  - R9.1 behavior and acceptance tests.
- `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_backtest_boundaries.py`
  - Boundary tests proving hot-path packages do not import backtest code.

Modify:

- `/Users/pratik.nandoskar/Documents/working/prescient/README.md`
  - Add a short R9.1 cold-path backtest note after implementation.

Do not modify:

- `prescient.signal` scoring/candidate logic.
- `prescient.risk` gates or position sizing.
- `prescient.broker` adapters.
- `prescient.runtime` live pipeline behavior.
- Data provider adapters.

## Public API

Add:

```python
def run_peer_readthrough_backtest(
    request: BacktestRunRequest,
    dataset: BacktestDataset,
) -> BacktestRunResult:
    ...
```

Key defaults:

- `strategy_type = "bullish_earnings_readthrough"`
- `evaluation_horizon_days = 1`
- `include_rejected_candidates = True`
- `include_trade_pnl = True`
- `positive_followthrough_threshold_pct = 1.0`
- `negative_followthrough_threshold_pct = -1.0`

Option P&L rule:

- Compute option P&L only when explicit historical entry and exit option quotes are present.
- If option quotes are missing, mark trade P&L as `not_evaluable`.
- Do not approximate option P&L from stock movement.

## Tasks

### Task 1: Save R9.1 PRD

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/docs/prd/09-backtest-r9-1-peer-readthrough-edge-prd.md`

- [ ] **Step 1: Create the PRD file from the conversation**

Copy the full R9.1 PRD from the conversation into the file above. Keep the title:

```markdown
# PRD: R9.1 Backtest the Peer-Read-Through Edge Before Risking Money
```

- [ ] **Step 2: Verify the PRD exists**

Run:

```bash
test -f docs/prd/09-backtest-r9-1-peer-readthrough-edge-prd.md
```

Expected: exit code `0`.

### Task 2: Write Failing Backtest Model Tests

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r9_1_peer_readthrough_backtest.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/models.py`

- [ ] **Step 1: Add tests for request defaults and fixture serialization**

Add tests that import these not-yet-existing models:

```python
from datetime import date

from prescient.backtest import (
    BacktestDataset,
    BacktestRunRequest,
    BacktestTradeExpression,
    HistoricalOptionQuote,
    HistoricalPricePoint,
)


def test_backtest_request_defaults_are_bounded_and_bullish() -> None:
    request = BacktestRunRequest(
        run_id="r9-1-fixture",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        max_events=50,
    )

    assert request.strategy_type == "bullish_earnings_readthrough"
    assert request.evaluation_horizon_days == 1
    assert request.include_rejected_candidates is True
    assert request.include_trade_pnl is True
    assert request.max_events == 50


def test_fixture_models_normalize_tickers_and_serialize() -> None:
    price = HistoricalPricePoint(ticker="ntnx", trading_date=date(2025, 6, 2), close=50.0)
    quote = HistoricalOptionQuote(
        ticker="ntnx",
        option_type="call",
        expiration_date=date(2025, 6, 20),
        trading_date=date(2025, 6, 2),
        bid=1.0,
        ask=1.2,
    )
    dataset = BacktestDataset(prices=[price], option_quotes=[quote])

    assert dataset.prices[0].ticker == "NTNX"
    assert dataset.option_quotes[0].option_type == BacktestTradeExpression.CALL_OPTION
    assert dataset.model_dump(mode="json")["prices"][0]["trading_date"] == "2025-06-02"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py::test_backtest_request_defaults_are_bounded_and_bullish tests/test_r9_1_peer_readthrough_backtest.py::test_fixture_models_normalize_tickers_and_serialize -q
```

Expected: fail with missing `prescient.backtest` imports.

### Task 3: Implement Backtest Models

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/__init__.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/models.py`

- [ ] **Step 1: Add model enums and request/data models**

Implement:

- `BacktestOutcome = "win" | "loss" | "flat" | "not_evaluable"`
- `BacktestTradeExpression = "STOCK" | "CALL_OPTION"`
- `BacktestRunRequest`
- `HistoricalPricePoint`
- `HistoricalOptionQuote`
- `BacktestDataset`
- `UnderlyingFollowThroughOutcome`
- `TradePnlOutcome`
- `BacktestSetupResult`
- `BacktestSummary`
- `BacktestRunResult`

Use `ConfigDict(frozen=True, extra="forbid")` and uppercase ticker validators.

- [ ] **Step 2: Export models**

Export all public R9.1 models from `src/prescient/backtest/__init__.py`.

- [ ] **Step 3: Run model tests**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py::test_backtest_request_defaults_are_bounded_and_bullish tests/test_r9_1_peer_readthrough_backtest.py::test_fixture_models_normalize_tickers_and_serialize -q
```

Expected: pass.

### Task 4: Write Failing Outcome Tests

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r9_1_peer_readthrough_backtest.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/outcomes.py`

- [ ] **Step 1: Add tests for underlying and trade outcomes**

Add tests covering:

```python
from datetime import date

from prescient.backtest import BacktestOutcome, BacktestTradeExpression, HistoricalOptionQuote
from prescient.backtest.outcomes import (
    calculate_option_trade_pnl,
    calculate_stock_trade_pnl,
    calculate_underlying_followthrough,
)


def test_underlying_followthrough_wins_loses_flats_and_missing_data() -> None:
    assert calculate_underlying_followthrough(
        ticker="NTNX",
        entry_price=50.0,
        exit_price=52.0,
        evaluation_start=date(2025, 6, 2),
        evaluation_end=date(2025, 6, 3),
    ).outcome == BacktestOutcome.WIN

    assert calculate_underlying_followthrough(
        ticker="NTNX",
        entry_price=50.0,
        exit_price=49.75,
        evaluation_start=date(2025, 6, 2),
        evaluation_end=date(2025, 6, 3),
    ).outcome == BacktestOutcome.FLAT

    assert calculate_underlying_followthrough(
        ticker="NTNX",
        entry_price=50.0,
        exit_price=48.0,
        evaluation_start=date(2025, 6, 2),
        evaluation_end=date(2025, 6, 3),
    ).outcome == BacktestOutcome.LOSS


def test_stock_trade_pnl_uses_entry_exit_quantity_and_fees() -> None:
    outcome = calculate_stock_trade_pnl(
        ticker="NTNX",
        expression=BacktestTradeExpression.STOCK,
        quantity=10,
        entry_price=50.0,
        exit_price=52.0,
        fees=1.0,
    )

    assert outcome.net_pnl == 19.0
    assert outcome.outcome == BacktestOutcome.WIN


def test_option_trade_pnl_requires_explicit_option_quotes() -> None:
    entry = HistoricalOptionQuote(
        ticker="NTNX",
        option_type="CALL_OPTION",
        expiration_date=date(2025, 6, 20),
        trading_date=date(2025, 6, 2),
        bid=1.0,
        ask=1.2,
    )
    exit_quote = entry.model_copy(update={"trading_date": date(2025, 6, 3), "bid": 1.8, "ask": 2.0})

    evaluable = calculate_option_trade_pnl(
        ticker="NTNX",
        quantity=1,
        entry_quote=entry,
        exit_quote=exit_quote,
        fees=0.0,
    )
    missing = calculate_option_trade_pnl(
        ticker="NTNX",
        quantity=1,
        entry_quote=entry,
        exit_quote=None,
        fees=0.0,
    )

    assert evaluable.net_pnl == 70.0
    assert evaluable.outcome == BacktestOutcome.WIN
    assert missing.outcome == BacktestOutcome.NOT_EVALUABLE
```

- [ ] **Step 2: Run outcome tests and verify RED**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py::test_underlying_followthrough_wins_loses_flats_and_missing_data tests/test_r9_1_peer_readthrough_backtest.py::test_stock_trade_pnl_uses_entry_exit_quantity_and_fees tests/test_r9_1_peer_readthrough_backtest.py::test_option_trade_pnl_requires_explicit_option_quotes -q
```

Expected: fail with missing `prescient.backtest.outcomes`.

### Task 5: Implement Outcome Calculators

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/outcomes.py`

- [ ] **Step 1: Implement deterministic outcome helpers**

Implement:

- `calculate_underlying_followthrough(...)`
- `calculate_stock_trade_pnl(...)`
- `calculate_option_trade_pnl(...)`

Rules:

- Underlying return: `(exit_price - entry_price) / entry_price * 100`.
- Bullish default thresholds: win `>= 1.0%`, loss `<= -1.0%`, otherwise flat.
- Stock net P&L: `(exit_price - entry_price) * quantity - fees`.
- Option midpoint: `(bid + ask) / 2`.
- Option net P&L: `(exit_mid - entry_mid) * quantity * 100 - fees`.
- Missing/invalid price, quote, or non-positive quantity returns `not_evaluable`.

- [ ] **Step 2: Run outcome tests**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py::test_underlying_followthrough_wins_loses_flats_and_missing_data tests/test_r9_1_peer_readthrough_backtest.py::test_stock_trade_pnl_uses_entry_exit_quantity_and_fees tests/test_r9_1_peer_readthrough_backtest.py::test_option_trade_pnl_requires_explicit_option_quotes -q
```

Expected: pass.

### Task 6: Write Failing Backtest Runner Tests

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_r9_1_peer_readthrough_backtest.py`
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/runner.py`

- [ ] **Step 1: Add fixture runner tests**

Add tests that build a small dataset with:

- one target upcoming event
- three completed peer results before the target
- target market data
- one call option
- entry/exit prices
- optional entry/exit option quotes

Assert:

- candidate-ready setup becomes a backtest setup result
- underlying outcome is win when exit price is higher
- option P&L is evaluable when quotes exist
- option P&L is `not_evaluable` when exit quote is missing
- rejected candidate is still included when `include_rejected_candidates=True`

- [ ] **Step 2: Run runner tests and verify RED**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py::test_backtest_runner_replays_candidate_and_computes_summary tests/test_r9_1_peer_readthrough_backtest.py::test_backtest_runner_marks_option_pnl_not_evaluable_without_exit_quote -q
```

Expected: fail with missing `run_peer_readthrough_backtest`.

### Task 7: Implement Backtest Runner

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/runner.py`
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/src/prescient/backtest/__init__.py`

- [ ] **Step 1: Implement `run_peer_readthrough_backtest`**

Implementation approach:

- Filter historical target events to `request.start_date <= earnings_date <= request.end_date`.
- Cap events at `request.max_events`.
- For each target event, call existing `evaluate_core_strategy(...)` with historical `upcoming_events`, `peer_results`, `target_market_data`, `options_chains`, and `current_date=target_event.earnings_date - 1 day`.
- For each resulting decision:
  - Build an underlying outcome from matching target entry/exit prices.
  - If candidate-ready and `include_trade_pnl=True`, compute stock or call-option P&L from explicit historical inputs.
  - Preserve rejected decisions when `include_rejected_candidates=True`.
- Build aggregate `BacktestSummary`.

- [ ] **Step 2: Export runner**

Export `run_peer_readthrough_backtest` from `src/prescient/backtest/__init__.py`.

- [ ] **Step 3: Run runner tests**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py -q
```

Expected: pass.

### Task 8: Add Boundary Tests

**Files:**
- Create: `/Users/pratik.nandoskar/Documents/working/prescient/tests/test_backtest_boundaries.py`

- [ ] **Step 1: Add import-boundary tests**

Add an AST-based test like existing boundary tests:

```python
from __future__ import annotations

import ast
from pathlib import Path


def test_hot_path_packages_do_not_import_backtest() -> None:
    hot_roots = [
        Path("src/prescient/signal"),
        Path("src/prescient/risk"),
        Path("src/prescient/broker"),
        Path("src/prescient/data"),
        Path("src/prescient/runtime"),
        Path("src/prescient/scheduler"),
    ]

    for root in hot_roots:
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            imports.extend(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )

            assert not any(
                imported == "prescient.backtest" or imported.startswith("prescient.backtest.")
                for imported in imports
            ), f"{path} imports backtest code: {imports}"
```

- [ ] **Step 2: Run boundary tests**

Run:

```bash
uv run pytest tests/test_backtest_boundaries.py -q
```

Expected: pass.

### Task 9: Documentation And Verification

**Files:**
- Modify: `/Users/pratik.nandoskar/Documents/working/prescient/README.md`

- [ ] **Step 1: Add README note**

Add a concise note that R9.1 backtests peer-read-through setups in a cold path, computes stock follow-through and trade P&L, and never places orders or changes live settings.

- [ ] **Step 2: Run targeted verification**

Run:

```bash
uv run pytest tests/test_r9_1_peer_readthrough_backtest.py tests/test_backtest_boundaries.py -q
```

Expected: pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: full suite green and Ruff clean. If unrelated pre-existing failures appear, record exact failing tests and still report the R9.1 targeted result separately.

## Assumptions

- The R9.1 PRD from the conversation is the source spec until the PRD file is saved.
- R9.1 is fixture/data-driven and does not add live provider integrations.
- Option P&L requires explicit historical option quotes; no stock-move proxy is allowed.
- Backtest runs are cold-path research and do not alter live settings, account risk, broker mode, or theme config.
- `prescient.backtest` may import existing signal models/functions, but hot-path packages must not import `prescient.backtest`.
