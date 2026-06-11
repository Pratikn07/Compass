"""Pinned-value tests for the cost model and scorecard math."""
from datetime import date, timedelta

import pytest

from compass.backtest.costs import (
    after_tax_equity,
    apply_side_cost,
    net_trade_return,
    tax_rate,
)
from compass.backtest.scorecard import (
    binomial_ci_95,
    cagr,
    max_drawdown,
    mean_median,
    sample_label,
    sharpe,
)
from compass.backtest.series import Series


def test_side_cost():
    assert apply_side_cost(100.0) == pytest.approx(99.9)


def test_tax_rate_boundary_at_365_days():
    entry = date(2020, 1, 1)
    assert tax_rate(entry, entry + timedelta(days=364)) == 0.35
    assert tax_rate(entry, entry + timedelta(days=365)) == 0.20


def test_after_tax_equity_taxes_gains_only():
    entry, exit = date(2020, 1, 1), date(2020, 6, 1)  # short-term
    # Gain: 100 -> 120, 20 gain taxed at 35% -> 13 kept -> 113
    assert after_tax_equity(120.0, 100.0, entry, exit) == pytest.approx(113.0)
    # Loss: no tax credit, passes through untouched
    assert after_tax_equity(80.0, 100.0, entry, exit) == 80.0


def test_net_trade_return_charges_both_sides_then_tax():
    entry, exit = date(2020, 1, 1), date(2020, 3, 1)
    # +10% gross, costs: 1.1 * 0.999^2 - 1 = 0.097802..., then 35% tax
    expected = (1.1 * 0.999**2 - 1) * 0.65
    assert net_trade_return(0.10, entry, exit) == pytest.approx(expected)
    # A loss is not flattered: costs still charged, no tax credit
    expected_loss = 0.9 * 0.999**2 - 1
    assert net_trade_return(-0.10, entry, exit) == pytest.approx(expected_loss)


def test_cagr_pinned():
    eq = Series([date(2010, 1, 1), date(2012, 1, 1)], [1.0, 1.21])
    # two years: sqrt(1.21) - 1 = 10% (within calendar-day tolerance)
    assert cagr(eq) == pytest.approx(0.10, abs=0.001)


def test_max_drawdown_pinned():
    dates = [date(2020, 1, i) for i in range(1, 6)]
    eq = Series(dates, [1.0, 1.5, 0.75, 1.2, 1.6])
    assert max_drawdown(eq) == pytest.approx(0.75 / 1.5 - 1)  # -50%


def test_sharpe_zero_vol_is_none_and_sign_is_right():
    assert sharpe([0.01, 0.01, 0.01]) is None
    assert sharpe([0.02, -0.01, 0.03, 0.01]) > 0
    assert sharpe([-0.02, 0.01, -0.03, -0.01]) < 0


def test_sample_labels_match_rulebook():
    assert sample_label(29) == "too_few"
    assert sample_label(30) == "suggestive"
    assert sample_label(150) == "moderate"
    assert sample_label(500) == "strong"


def test_mean_median():
    mean, median = mean_median([1.0, 2.0, 10.0])
    assert mean == pytest.approx(13 / 3)
    assert median == 2.0
    assert mean_median([]) == (None, None)


def test_binomial_ci():
    lo, hi = binomial_ci_95(60, 100)
    assert lo == pytest.approx(0.6 - 1.96 * (0.6 * 0.4 / 100) ** 0.5)
    assert hi < 0.7960001
    assert binomial_ci_95(0, 0) is None
