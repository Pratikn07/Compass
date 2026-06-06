from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


def test_prediction_normalizes_ticker_and_accepts_directions() -> None:
    from prescient.edge.models import Prediction, PredictionDirection

    pred = Prediction(
        ticker="mu",
        as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.UP,
        predicted_move_pct=4.0,
        confidence=0.55,
        source="reaction_aware_peer",
    )
    assert pred.ticker == "MU"
    assert pred.direction == PredictionDirection.UP
    assert pred.predicted_move_pct == 4.0
    assert pred.confidence == 0.55


def test_prediction_rejects_out_of_range_confidence() -> None:
    from prescient.edge.models import Prediction, PredictionDirection

    with pytest.raises(ValidationError):
        Prediction(
            ticker="MU",
            as_of_date=date(2024, 6, 25),
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=1.5,
            source="x",
        )


def test_option_quote_is_frozen_and_keeps_strike() -> None:
    from prescient.edge.models import OptionQuote

    quote = OptionQuote(
        ticker="MU",
        option_type="CALL",
        strike=100.0,
        expiration_date=date(2024, 7, 19),
        quote_date=date(2024, 6, 25),
        bid=3.9,
        ask=4.1,
    )
    assert quote.strike == 100.0
    assert quote.mid == pytest.approx(4.0)
    with pytest.raises(ValidationError):
        quote.bid = 5.0  # type: ignore[misc]


def test_realized_and_event_score_normalize_ticker() -> None:
    from prescient.edge.models import EventScore, RealizedMove

    rm = RealizedMove(
        ticker="mu", pre_report_close=100.0, post_report_close=106.0,
        realized_move_pct=6.0,
    )
    assert rm.ticker == "MU"
    es = EventScore(
        ticker="nvda", as_of_date=date(2024, 6, 25), source="x", evaluable=False,
    )
    assert es.ticker == "NVDA"


def test_prediction_sell_straddle_defaults_false_and_settable() -> None:
    from datetime import date
    from prescient.edge.models import Prediction, PredictionDirection

    p = Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="short_vol",
    )
    assert p.sell_straddle is False
    p2 = Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="short_vol", sell_straddle=True,
    )
    assert p2.sell_straddle is True


def test_event_score_stayed_within_implied_defaults_none() -> None:
    from datetime import date
    from prescient.edge.models import EventScore

    s = EventScore(
        ticker="MU", as_of_date=date(2024, 6, 25), source="x", evaluable=False,
    )
    assert s.stayed_within_implied is None
