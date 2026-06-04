# PRD: R9.1 Backtest the Peer-Read-Through Edge Before Risking Money

## Summary

R9.1 adds a cold-path backtest capability for the bullish peer-read-through
strategy. Before risking real money, the system must replay historical setups and
answer whether the next name in a theme actually followed through after peers
reported, and whether the strategy expression would have produced positive P&L.

This is research and evaluation infrastructure only. It must not change live
runtime orchestration, risk gates, broker behavior, production settings, or data
provider adapters.

## Goals

- Replay historical peer-read-through setups from explicit fixture data.
- Measure target underlying follow-through after the target earnings event.
- Measure trade P&L for stock and call-option expressions when required price or
  quote data is available.
- Represent candidate-ready, rejected, flat, loss, win, and not-evaluable cases.
- Summarize results by target, theme, expression, rejection reason, and missing
  data so humans can decide whether the edge is real enough to pursue.
- Keep the backtest package out of hot-path runtime, broker, risk, and live data
  provider flows.

## Non-Goals

- No live Finnhub, broker, Supabase, or market-data calls.
- No scheduler/runtime provider fetching.
- No mutation of deterministic strategy settings from backtest results.
- No LLM trade approval or analyst prompt generation.
- No option-price approximation from underlying moves.
- No portfolio optimization, multi-leg option strategy simulation, or slippage
  model beyond explicit quote-based entry/exit prices.

## Scope

Add a new `prescient.backtest` package that accepts a bounded
`BacktestRunRequest` and a `BacktestDataset` of historical inputs:

- strategy universe
- target earnings calendar events
- completed peer earnings results
- target market data
- option chains used by the signal engine
- historical target close prices
- historical option quotes
- optional strategy settings snapshot

The backtest runner will replay target setups through the existing
`evaluate_core_strategy` signal engine, then compute outcomes from explicit
historical price and quote data.

## Functional Requirements

### Request Bounds

`BacktestRunRequest` must include:

- `run_id`
- `start_date`
- `end_date`
- `max_events`
- `strategy_type`, defaulting to `bullish_earnings_readthrough`
- `evaluation_horizon_days`, defaulting to `1`
- `include_rejected_candidates`, defaulting to `True`
- `include_trade_pnl`, defaulting to `True`
- positive and negative underlying follow-through thresholds

The request must reject invalid date ranges and non-positive event/horizon
bounds.

### Historical Data Model

The dataset must be explicit, serializable, and deterministic. Tickers must be
normalized to uppercase. Backtest models must avoid secrets, provider payloads,
broker/account fields, and authorization material.

### Replay Behavior

For each target event within the requested date range:

- Use the existing deterministic signal engine.
- Pass only historical fixture data.
- Prevent look-ahead bias by using peer results with earnings dates before the
  target earnings date.
- Respect `max_events`.
- Keep rejected candidates when requested.

### Underlying Follow-Through

Compute target underlying return from explicit entry and exit close prices:

- `win` when return is at or above the positive threshold.
- `loss` when return is at or below the negative threshold.
- `flat` when the return is between thresholds.
- `not_evaluable` when required prices are missing or invalid.

### Trade P&L

For stock expressions:

- Compute P&L from explicit entry and exit prices, quantity, and fees.

For call-option expressions:

- Compute P&L only when explicit historical entry and exit option quotes are
  present.
- Use quote midpoints for entry and exit valuation.
- Mark trade P&L as `not_evaluable` when option quotes are missing or invalid;
  this is the required behavior when quotes are missing.
- Do not infer option P&L from target stock movement.

### Summary

The run result must include:

- total setups
- candidate-ready count
- rejected count
- not-evaluable count
- underlying win/loss/flat counts
- trade win/loss/flat/not-evaluable counts
- average and median underlying return
- average and median net P&L
- buckets by ticker, theme, expression, and rejection reason
- warnings for missing data or unsupported cases

## Boundary Requirements

- `prescient.backtest` may import deterministic signal models and
  `evaluate_core_strategy`.
- Hot-path packages must not import `prescient.backtest`.
- Backtest code must not import broker adapters, runtime orchestration, alert
  dispatch, scheduler loops, live data providers, or environment loaders.

## Acceptance Criteria

- A fixture-driven backtest runs without network calls.
- Candidate-ready, rejected, and not-evaluable cases are represented.
- Stock P&L is computed only from explicit historical prices.
- Option P&L is computed only from explicit historical option quotes.
- Missing option quotes do not approximate option outcomes.
- Serialized results contain no secrets, raw provider payloads, prompts,
  authorization headers, broker account terms, or live order material.
- Boundary tests prove hot-path packages do not import `prescient.backtest`.

## Verification

- `uv run pytest tests/test_r9_1_peer_readthrough_backtest.py tests/test_backtest_boundaries.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
