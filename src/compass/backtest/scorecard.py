"""Scorecard metrics (rulebook §5.4): CAGR, Sharpe, max drawdown, median AND
mean, counts, sample-size honesty labels. Pure math, no I/O."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date

from .series import Series

TRADING_DAYS_PER_YEAR = 252


def sample_label(n: int) -> str:
    if n < 30:
        return "too_few"
    if n < 150:
        return "suggestive"
    if n < 500:
        return "moderate"
    return "strong"


def cagr(equity: Series) -> float | None:
    if len(equity) < 2 or equity.values[0] <= 0:
        return None
    years = (equity.dates[-1] - equity.dates[0]).days / 365.25
    if years <= 0:
        return None
    return (equity.values[-1] / equity.values[0]) ** (1 / years) - 1


def period_returns(equity: Series) -> list[float]:
    return [
        equity.values[i] / equity.values[i - 1] - 1
        for i in range(1, len(equity))
        if equity.values[i - 1] > 0
    ]


def sharpe(monthly_returns: list[float]) -> float | None:
    """Annualized Sharpe from monthly returns (rf=0; the cash leg already
    earns the T-bill proxy inside the equity curve)."""
    n = len(monthly_returns)
    if n < 2:
        return None
    mean = sum(monthly_returns) / n
    var = sum((r - mean) ** 2 for r in monthly_returns) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    return (mean / sd) * math.sqrt(12)


def max_drawdown(equity: Series) -> float | None:
    """Worst peak-to-trough decline, as a negative fraction."""
    if not equity.values:
        return None
    peak = equity.values[0]
    worst = 0.0
    for v in equity.values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


@dataclass(frozen=True)
class EquityScore:
    name: str
    start: date
    end: date
    cagr: float | None
    sharpe: float | None
    max_drawdown: float | None
    n_periods: int
    final_equity: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        return d


def score_equity(name: str, monthly_equity: Series) -> EquityScore:
    rets = period_returns(monthly_equity)
    return EquityScore(
        name=name,
        start=monthly_equity.dates[0],
        end=monthly_equity.dates[-1],
        cagr=cagr(monthly_equity),
        sharpe=sharpe(rets),
        max_drawdown=max_drawdown(monthly_equity),
        n_periods=len(rets),
        final_equity=monthly_equity.values[-1],
    )


def mean_median(xs: list[float]) -> tuple[float | None, float | None]:
    if not xs:
        return None, None
    s = sorted(xs)
    n = len(s)
    median = s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2
    return sum(s) / n, median


def binomial_ci_95(successes: int, n: int) -> tuple[float, float] | None:
    """Normal-approximation 95% CI for a proportion."""
    if n == 0:
        return None
    p = successes / n
    half = 1.96 * math.sqrt(p * (1 - p) / n)
    return max(p - half, 0.0), min(p + half, 1.0)
