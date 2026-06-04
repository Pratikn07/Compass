"""Cold-path performance analytics for backtests and learning reports."""

from prescient.analytics.models import (
    BenchmarkComparison,
    BuyHoldBenchmark,
    MetricsEvaluationStatus,
    PerformanceAnalyticsRequest,
    PerformanceMetrics,
    PerformanceObservation,
)
from prescient.analytics.performance import calculate_performance_metrics, compare_to_buy_hold

__all__ = [
    "BenchmarkComparison",
    "BuyHoldBenchmark",
    "MetricsEvaluationStatus",
    "PerformanceAnalyticsRequest",
    "PerformanceMetrics",
    "PerformanceObservation",
    "calculate_performance_metrics",
    "compare_to_buy_hold",
]
