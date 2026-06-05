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
