from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from statistics import mean, stdev

from prescient.analytics.models import (
    BenchmarkComparison,
    BuyHoldBenchmark,
    MetricsEvaluationStatus,
    PerformanceAnalyticsRequest,
    PerformanceMetrics,
    PerformanceObservation,
)


def calculate_performance_metrics(request: PerformanceAnalyticsRequest) -> PerformanceMetrics:
    excluded = Counter[str]()
    total_observations = len(request.observations)

    if request.starting_equity <= 0:
        excluded["non_positive_equity"] += 1
        return PerformanceMetrics(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            total_observation_count=total_observations,
            excluded_counts=dict(excluded),
        )

    evaluable = _evaluable_strategy_observations(request.observations, excluded)
    if not evaluable:
        excluded["insufficient_return_series"] += 1
        return PerformanceMetrics(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            total_observation_count=total_observations,
            excluded_counts=dict(excluded),
        )

    pnl_values = [observation.strategy_net_pnl for observation in evaluable]
    typed_pnls = [float(value) for value in pnl_values if value is not None]
    win_count = sum(1 for pnl in typed_pnls if pnl > 0)
    loss_count = sum(1 for pnl in typed_pnls if pnl < 0)
    flat_count = sum(1 for pnl in typed_pnls if pnl == 0)
    closed_count = len(typed_pnls)
    total_net_pnl = sum(typed_pnls)
    daily_returns = _daily_returns(
        observations=evaluable,
        starting_equity=request.starting_equity,
    )
    sharpe_ratio, sharpe_status = _sharpe_ratio(
        daily_returns=daily_returns,
        annual_risk_free_rate=request.annual_risk_free_rate,
        periods_per_year=request.periods_per_year,
        excluded=excluded,
    )
    max_drawdown = _max_drawdown_pct(
        observations=evaluable,
        starting_equity=request.starting_equity,
    )

    return PerformanceMetrics(
        status=MetricsEvaluationStatus.EVALUABLE,
        total_observation_count=total_observations,
        closed_evaluable_outcome_count=closed_count,
        win_count=win_count,
        loss_count=loss_count,
        flat_count=flat_count,
        win_rate=win_count / closed_count if closed_count else None,
        total_net_pnl=total_net_pnl,
        total_return_pct=(total_net_pnl / request.starting_equity) * 100,
        max_drawdown_pct=max_drawdown,
        max_drawdown_status=MetricsEvaluationStatus.EVALUABLE,
        sharpe_ratio=sharpe_ratio,
        sharpe_status=sharpe_status,
        daily_return_count=len(daily_returns),
        excluded_counts=dict(excluded),
    )


def compare_to_buy_hold(request: PerformanceAnalyticsRequest) -> BenchmarkComparison:
    strategy_metrics = calculate_performance_metrics(request)
    excluded = Counter[str]()

    if request.starting_equity <= 0:
        excluded["non_positive_equity"] += 1
        benchmark = BuyHoldBenchmark(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            excluded_counts=dict(excluded),
        )
        return BenchmarkComparison(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            benchmark_status=benchmark.status,
            strategy_metrics=strategy_metrics,
            buy_hold_benchmark=benchmark,
            excluded_counts=dict(excluded),
        )

    matched_strategy_pnl: list[float] = []
    benchmark_pnl: list[float] = []
    for observation in request.observations:
        if not _is_number(observation.strategy_net_pnl):
            excluded["missing_strategy_pnl"] += 1
            continue
        if not _is_positive_number(observation.allocated_capital):
            excluded["non_positive_allocated_capital"] += 1
            continue
        if not _is_positive_number(observation.benchmark_entry_price) or not _is_number(
            observation.benchmark_exit_price
        ):
            excluded["missing_benchmark_price"] += 1
            continue

        shares = observation.allocated_capital / float(observation.benchmark_entry_price)
        benchmark_pnl.append(
            shares
            * (
                float(observation.benchmark_exit_price)
                - float(observation.benchmark_entry_price)
            )
        )
        matched_strategy_pnl.append(float(observation.strategy_net_pnl))

    if not benchmark_pnl:
        excluded["missing_benchmark_price"] += 0
        benchmark = BuyHoldBenchmark(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            observation_count=0,
            excluded_counts=dict(excluded),
        )
        return BenchmarkComparison(
            status=MetricsEvaluationStatus.NOT_EVALUABLE,
            benchmark_status=benchmark.status,
            strategy_metrics=strategy_metrics,
            buy_hold_benchmark=benchmark,
            excluded_counts=dict(excluded),
        )

    strategy_return = (sum(matched_strategy_pnl) / request.starting_equity) * 100
    benchmark_return = (sum(benchmark_pnl) / request.starting_equity) * 100
    benchmark = BuyHoldBenchmark(
        status=MetricsEvaluationStatus.EVALUABLE,
        observation_count=len(benchmark_pnl),
        total_net_pnl=sum(benchmark_pnl),
        total_return_pct=benchmark_return,
        excluded_counts=dict(excluded),
    )

    return BenchmarkComparison(
        status=MetricsEvaluationStatus.EVALUABLE,
        strategy_total_return_pct=strategy_return,
        buy_hold_total_return_pct=benchmark_return,
        excess_return_pct=strategy_return - benchmark_return,
        beats_buy_and_hold=strategy_return > benchmark_return,
        benchmark_status=benchmark.status,
        strategy_metrics=strategy_metrics,
        buy_hold_benchmark=benchmark,
        excluded_counts=dict(excluded),
    )


def _evaluable_strategy_observations(
    observations: list[PerformanceObservation],
    excluded: Counter[str],
) -> list[PerformanceObservation]:
    evaluable: list[PerformanceObservation] = []
    for observation in observations:
        if not _is_number(observation.strategy_net_pnl):
            excluded["missing_strategy_pnl"] += 1
            continue
        evaluable.append(observation)
    return evaluable


def _daily_returns(
    *,
    observations: list[PerformanceObservation],
    starting_equity: float,
) -> list[float]:
    pnl_by_date = defaultdict[object, float](float)
    for observation in observations:
        if observation.strategy_net_pnl is None:
            continue
        pnl_by_date[observation.exit_date] += float(observation.strategy_net_pnl)

    returns: list[float] = []
    equity = starting_equity
    for exit_date in sorted(pnl_by_date):
        if equity <= 0:
            break
        daily_pnl = pnl_by_date[exit_date]
        returns.append(daily_pnl / equity)
        equity += daily_pnl
    return returns


def _max_drawdown_pct(
    *,
    observations: list[PerformanceObservation],
    starting_equity: float,
) -> float:
    peak = starting_equity
    equity = starting_equity
    max_drawdown = 0.0
    for observation in sorted(
        observations,
        key=lambda item: (item.exit_date, item.observation_id),
    ):
        if observation.strategy_net_pnl is None:
            continue
        equity += float(observation.strategy_net_pnl)
        if equity > peak:
            peak = equity
        if peak <= 0:
            continue
        drawdown = ((peak - equity) / peak) * 100
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _sharpe_ratio(
    *,
    daily_returns: list[float],
    annual_risk_free_rate: float,
    periods_per_year: int,
    excluded: Counter[str],
) -> tuple[float | None, MetricsEvaluationStatus]:
    if len(daily_returns) < 2:
        excluded["insufficient_return_series"] += 1
        return None, MetricsEvaluationStatus.NOT_EVALUABLE

    return_stdev = stdev(daily_returns)
    if return_stdev == 0:
        excluded["zero_return_variance"] += 1
        return None, MetricsEvaluationStatus.NOT_EVALUABLE

    daily_risk_free_rate = annual_risk_free_rate / periods_per_year
    excess_returns = [daily_return - daily_risk_free_rate for daily_return in daily_returns]
    return (
        (mean(excess_returns) / return_stdev) * sqrt(periods_per_year),
        MetricsEvaluationStatus.EVALUABLE,
    )


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_positive_number(value: object) -> bool:
    return _is_number(value) and float(value) > 0
