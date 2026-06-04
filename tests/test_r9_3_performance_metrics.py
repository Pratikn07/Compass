from __future__ import annotations

from datetime import date

import pytest

from prescient.analytics import (
    MetricsEvaluationStatus,
    PerformanceAnalyticsRequest,
    PerformanceObservation,
    calculate_performance_metrics,
    compare_to_buy_hold,
)
from prescient.backtest import (
    BacktestDataset,
    BacktestOutcome,
    BacktestRunRequest,
    BacktestSetupResult,
    BacktestTradeExpression,
    TradePnlOutcome,
    run_peer_readthrough_backtest,
)


def test_performance_metrics_compute_win_rate_drawdown_sharpe_and_return() -> None:
    request = PerformanceAnalyticsRequest(
        starting_equity=10_000.0,
        observations=[
            PerformanceObservation(
                observation_id="trade-1",
                ticker="ntnx",
                entry_date=date(2025, 6, 2),
                exit_date=date(2025, 6, 3),
                allocated_capital=1_000.0,
                strategy_net_pnl=200.0,
                benchmark_entry_price=10.0,
                benchmark_exit_price=12.0,
            ),
            PerformanceObservation(
                observation_id="trade-2",
                ticker="crm",
                entry_date=date(2025, 6, 3),
                exit_date=date(2025, 6, 4),
                allocated_capital=1_000.0,
                strategy_net_pnl=-500.0,
                benchmark_entry_price=20.0,
                benchmark_exit_price=18.0,
            ),
            PerformanceObservation(
                observation_id="trade-3",
                ticker="adbe",
                entry_date=date(2025, 6, 4),
                exit_date=date(2025, 6, 5),
                allocated_capital=1_000.0,
                strategy_net_pnl=300.0,
                benchmark_entry_price=50.0,
                benchmark_exit_price=51.0,
            ),
        ],
    )

    metrics = calculate_performance_metrics(request)
    comparison = compare_to_buy_hold(request)

    assert metrics.status == MetricsEvaluationStatus.EVALUABLE
    assert metrics.closed_evaluable_outcome_count == 3
    assert metrics.win_count == 2
    assert metrics.loss_count == 1
    assert metrics.flat_count == 0
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.total_net_pnl == 0.0
    assert metrics.total_return_pct == 0.0
    assert metrics.max_drawdown_pct == pytest.approx(4.90196, rel=1e-4)
    assert metrics.sharpe_status == MetricsEvaluationStatus.EVALUABLE
    assert metrics.sharpe_ratio is not None
    assert comparison.status == MetricsEvaluationStatus.EVALUABLE
    assert comparison.buy_hold_total_return_pct == pytest.approx(1.2)
    assert comparison.excess_return_pct == pytest.approx(-1.2)
    assert comparison.beats_buy_and_hold is False


def test_metrics_preserve_structured_not_evaluable_reasons() -> None:
    non_positive_equity = calculate_performance_metrics(
        PerformanceAnalyticsRequest(
            starting_equity=0.0,
            observations=[
                PerformanceObservation(
                    observation_id="trade-1",
                    ticker="ntnx",
                    entry_date=date(2025, 6, 2),
                    exit_date=date(2025, 6, 3),
                    allocated_capital=1_000.0,
                    strategy_net_pnl=50.0,
                    benchmark_entry_price=50.0,
                    benchmark_exit_price=51.0,
                )
            ],
        )
    )
    insufficient_returns = calculate_performance_metrics(
        PerformanceAnalyticsRequest(
            observations=[
                PerformanceObservation(
                    observation_id="trade-1",
                    ticker="ntnx",
                    entry_date=date(2025, 6, 2),
                    exit_date=date(2025, 6, 3),
                    allocated_capital=1_000.0,
                    strategy_net_pnl=None,
                    benchmark_entry_price=50.0,
                    benchmark_exit_price=51.0,
                )
            ],
        )
    )

    assert non_positive_equity.status == MetricsEvaluationStatus.NOT_EVALUABLE
    assert non_positive_equity.excluded_counts["non_positive_equity"] == 1
    assert insufficient_returns.status == MetricsEvaluationStatus.NOT_EVALUABLE
    assert insufficient_returns.excluded_counts["missing_strategy_pnl"] == 1
    assert insufficient_returns.excluded_counts["insufficient_return_series"] == 1
    assert insufficient_returns.sharpe_status == MetricsEvaluationStatus.NOT_EVALUABLE


def test_backtest_summary_includes_metrics_and_matched_buy_hold_benchmark() -> None:
    request = BacktestRunRequest(
        run_id="r9-3-fixture",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
    )
    dataset = BacktestDataset(
        setup_results=[
            BacktestSetupResult(
                setup_id="setup-1",
                ticker="ntnx",
                entry_date=date(2025, 6, 2),
                exit_date=date(2025, 6, 3),
                strategy_status="candidate_ready_for_analyst",
                expression=BacktestTradeExpression.CALL_OPTION,
                allocated_capital=110.0,
                underlying_entry_price=50.0,
                underlying_exit_price=52.0,
                trade_pnl=TradePnlOutcome(
                    ticker="NTNX",
                    expression=BacktestTradeExpression.CALL_OPTION,
                    quantity=1,
                    net_pnl=70.0,
                    outcome=BacktestOutcome.WIN,
                ),
            )
        ]
    )

    result = run_peer_readthrough_backtest(request, dataset)

    assert result.summary.win_rate == 1.0
    assert result.summary.total_return_pct == pytest.approx(0.7)
    assert result.summary.buy_hold_total_return_pct == pytest.approx(0.044)
    assert result.summary.excess_return_pct == pytest.approx(0.656)
    assert result.summary.beats_buy_and_hold is True
    assert result.summary.benchmark_status == MetricsEvaluationStatus.EVALUABLE
