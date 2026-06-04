# PRD: R9.3 Backtest Performance Metrics and Buy-and-Hold Benchmark

## Ownership

Owner: GPT

Source note: Requirement from GPT: add backtest metrics for win rate, max drawdown, Sharpe, and whether the strategy beats buy-and-hold.

## Objective

Add deterministic, cold-path performance analytics for R9 backtests.

R9.3 answers:

```text
Did the backtested strategy win often enough, avoid unacceptable drawdowns, produce a useful risk-adjusted return, and beat simply buying and holding the same target over the same trade window?
```

The analytics layer must compute win rate, max drawdown, Sharpe ratio, strategy total return, matched target buy-and-hold return, excess return, and whether the strategy beat the benchmark.

## Background

R9.1 introduces cold-path backtesting for the peer read-through strategy before risking money. R6.2 already computes realized win/loss diagnostics from prior journal outcomes. R9.3 turns performance analytics into a shared deterministic layer so backtests and learning reports can reuse the same metric semantics without moving analytics into the hot path.

The buy-and-hold baseline is matched target buy-and-hold: buy the same target ticker at the strategy entry date/time and exit at the same strategy exit date or evaluation horizon. For option trades, the benchmark uses the strategy capital at risk, such as option premium paid, to buy fractional underlying shares.

## Functional Requirements

### R9.3.1 Cold-Path Analytics Boundary

Performance analytics must live in a cold-path package such as `prescient.analytics`.

The following packages must not import `prescient.analytics` or `prescient.backtest`:

- `prescient.signal`
- `prescient.risk`
- `prescient.broker`
- `prescient.data`
- hot runtime and scheduler modules

Analytics code must not call brokers, fetch live market data, place orders, mutate risk limits, or alter execution mode.

### R9.3.2 Performance Observation Model

Analytics must accept structured observations with fields equivalent to:

```python
class PerformanceObservation(BaseModel):
    observation_id: str
    ticker: str
    entry_date: date
    exit_date: date
    allocated_capital: float
    strategy_net_pnl: float | None
    benchmark_entry_price: float | None
    benchmark_exit_price: float | None
```

Tickers must normalize to uppercase. Missing P&L or benchmark prices must be counted as structured exclusions, not guessed.

### R9.3.3 Metrics Contract

Analytics must return metrics equivalent to:

- total observation count
- closed evaluable outcome count
- win count
- loss count
- flat count
- win rate
- total net P&L
- total return percentage
- max drawdown percentage
- Sharpe ratio
- structured exclusion counts

Win rate is `wins / closed_evaluable_outcomes`, where closed evaluable outcomes include wins, losses, and flats.

### R9.3.4 Drawdown

Max drawdown must be computed from an ordered equity curve using peak-to-trough percentage decline.

The default starting equity is `$10,000`. A non-positive starting equity must return a structured `not_evaluable` status.

### R9.3.5 Sharpe Ratio

Sharpe ratio must be computed from daily portfolio returns, annualized with `sqrt(252)`.

The annual risk-free rate defaults to `0.0` and must be configurable per request.

If fewer than two return points exist, or if return variance is zero, Sharpe must be `not_evaluable` with a structured reason.

### R9.3.6 Buy-and-Hold Benchmark

For each observation, buy-and-hold P&L is:

```text
allocated_capital / benchmark_entry_price * (benchmark_exit_price - benchmark_entry_price)
```

The benchmark must use the same target ticker, same entry date, same exit date or horizon, and same allocated capital as the strategy observation.

Missing benchmark entry/exit prices or non-positive allocated capital must exclude that observation from benchmark comparison.

### R9.3.7 Backtest Summary Integration

R9 backtest summaries must include:

- `win_rate`
- `max_drawdown_pct`
- `sharpe_ratio`
- `total_return_pct`
- `buy_hold_total_return_pct`
- `beats_buy_and_hold`
- `excess_return_pct`
- `benchmark_status`

`beats_buy_and_hold` is true only when strategy total return is greater than matched target buy-and-hold total return over the same evaluable observations.

### R9.3.8 R6.2 Reuse

R6.2 learning reports must reuse shared analytics where metric semantics are identical, especially closed outcome counts and win rate.

Existing R6.2 report field names and behavior must not regress.

## Acceptance Criteria

- Unit tests cover win rate, max drawdown, Sharpe, total return, missing P&L, missing benchmark prices, non-positive equity, insufficient return series, and zero return variance.
- Backtest integration tests prove R9 results include R9.3 metrics and matched target buy-and-hold comparison.
- R6.2 regression tests prove existing learning report metrics remain unchanged after shared analytics adoption.
- Boundary tests prove hot-path packages do not import analytics or backtest code.

## Non-Goals

- UI charts or dashboards.
- Live monitoring.
- Broker/account integration.
- Parameter auto-tuning.
- Inferring missing option or underlying prices.
- Using broad market ETFs as the R9.3 benchmark.
