from __future__ import annotations

from datetime import date

import pytest

from prescient.edge.models import (
    EventContext,
    OptionQuote,
    Prediction,
    PredictionDirection,
    RealizedMove,
)


def _quote(option_type):
    return OptionQuote(
        ticker="MU", option_type=option_type, strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=date(2024, 6, 25),
        bid=3.9, ask=4.1,
    )


def _ctx(realized_pct):
    return EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        realized_move=RealizedMove(
            ticker="MU", pre_report_close=100.0,
            post_report_close=100.0 * (1 + realized_pct / 100.0),
            realized_move_pct=realized_pct,
        ),
    )


def _pred(direction):
    return Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25), direction=direction,
        predicted_move_pct=4.0, confidence=0.55, source="reaction_aware_peer",
    )


def test_score_direction_correct_but_under_implied_does_not_beat() -> None:
    from prescient.edge.scorer import score_event

    # implied 8%, realized +6%: direction right, but did NOT beat implied
    score = score_event(prediction=_pred(PredictionDirection.UP), context=_ctx(6.0))
    assert score.evaluable is True
    assert score.direction_correct is True
    assert score.beat_implied is False
    assert score.implied_move_pct == pytest.approx(8.0)
    assert score.realized_move_pct == pytest.approx(6.0)
    assert score.option_pnl is not None


def test_score_beats_implied_on_large_move() -> None:
    from prescient.edge.scorer import score_event

    score = score_event(prediction=_pred(PredictionDirection.UP), context=_ctx(12.0))
    assert score.direction_correct is True
    assert score.beat_implied is True


def test_score_not_evaluable_when_realized_missing() -> None:
    from prescient.edge.scorer import score_event

    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        realized_move=None,
    )
    score = score_event(prediction=_pred(PredictionDirection.UP), context=ctx)
    assert score.evaluable is False
    assert score.not_evaluable_reason is not None
    assert score.direction_correct is None


def test_score_none_prediction_has_no_option_pnl() -> None:
    from prescient.edge.scorer import score_event

    score = score_event(prediction=_pred(PredictionDirection.NONE), context=_ctx(6.0))
    assert score.evaluable is True
    assert score.option_pnl is None


def test_score_wrong_direction_is_not_correct_and_does_not_beat_implied() -> None:
    from prescient.edge.scorer import score_event

    # Predict UP but stock fell -12%: direction wrong, and beat_implied must be False
    # (a wrong-direction move never "beats" the implied move on the predicted side).
    score = score_event(prediction=_pred(PredictionDirection.UP), context=_ctx(-12.0))
    assert score.evaluable is True
    assert score.direction_correct is False
    assert score.beat_implied is False


def test_score_directional_prediction_without_atm_call_has_no_option_pnl() -> None:
    from datetime import date

    from prescient.edge.scorer import score_event

    # atm_put present, atm_call missing -> implied move cannot be computed (needs both),
    # so the event is not evaluable rather than silently scored. Documents skip-not-guess.
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=None, atm_put=_quote("PUT"),
        realized_move=RealizedMove(
            ticker="MU", pre_report_close=100.0, post_report_close=106.0,
            realized_move_pct=6.0,
        ),
    )
    score = score_event(prediction=_pred(PredictionDirection.UP), context=ctx)
    # implied move needs BOTH call and put; missing call -> not evaluable
    assert score.evaluable is False
    assert score.not_evaluable_reason == "missing_implied_move"
    assert score.option_pnl is None
