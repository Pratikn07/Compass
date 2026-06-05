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
