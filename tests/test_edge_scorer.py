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


def test_sell_vol_small_move_scores_short_pnl_and_stayed_within() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=103.0, realized_move_pct=3.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                      confidence=0.5, source="short_vol", sell_straddle=True)
    s = score_event(prediction=pred, context=ctx)
    assert s.evaluable is True
    assert s.stayed_within_implied is True       # 3% < 8%
    assert s.option_pnl is not None
    assert s.direction_correct is None
    assert s.beat_implied is None


def test_sell_vol_big_move_not_stayed_within_and_capped_loss() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=120.0, realized_move_pct=20.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                      confidence=0.5, source="short_vol", sell_straddle=True)
    s = score_event(prediction=pred, context=ctx)
    assert s.stayed_within_implied is False
    assert s.option_pnl is not None
    assert s.option_pnl.net_pnl < 0


def _vr_quote(option_type, quote_date, close):
    return OptionQuote(
        ticker="MU", option_type=option_type, strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=quote_date,
        bid=close, ask=close,
    )


def _vr_ctx(**overrides):
    entry_d, exit_d = date(2024, 6, 18), date(2024, 6, 25)
    base = dict(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=exit_d,
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        entry_as_of_date=entry_d,
        vol_ramp_entry_call=_vr_quote("CALL", entry_d, 2.0),
        vol_ramp_entry_put=_vr_quote("PUT", entry_d, 2.0),
        vol_ramp_exit_call=_vr_quote("CALL", exit_d, 3.0),
        vol_ramp_exit_put=_vr_quote("PUT", exit_d, 3.0),
        realized_move=RealizedMove(
            ticker="MU", pre_report_close=100.0, post_report_close=103.0,
            realized_move_pct=3.0,
        ),
    )
    base.update(overrides)
    return EventContext(**base)


def _vr_pred():
    return Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="vol_ramp", buy_vol_ramp=True,
    )


def test_score_vol_ramp_computes_pnl_from_entry_and_exit_straddles() -> None:
    from prescient.edge.scorer import score_event

    # entry 2.0+2.0=4.0 ; exit 3.0+3.0=6.0 ; 5%/side haircut:
    # net = 6*0.95 - 4*1.05 = 1.5 -> 37.5% on premium
    s = score_event(prediction=_vr_pred(), context=_vr_ctx())
    assert s.evaluable is True
    assert s.direction_correct is None
    assert s.beat_implied is None
    assert s.stayed_within_implied is None
    assert s.option_pnl is not None
    assert s.option_pnl.return_pct == pytest.approx(37.5)
    # implied/realized are reported as diagnostics only
    assert s.implied_move_pct == pytest.approx(8.0)
    assert s.realized_move_pct == pytest.approx(3.0)


def test_score_vol_ramp_decayed_exit_is_negative() -> None:
    from prescient.edge.scorer import score_event

    exit_d = date(2024, 6, 25)
    ctx = _vr_ctx(
        vol_ramp_exit_call=_vr_quote("CALL", exit_d, 1.5),
        vol_ramp_exit_put=_vr_quote("PUT", exit_d, 1.5),
    )
    s = score_event(prediction=_vr_pred(), context=ctx)
    assert s.evaluable is True
    assert s.option_pnl is not None
    assert s.option_pnl.return_pct < 0


def test_score_vol_ramp_missing_leg_not_evaluable() -> None:
    from prescient.edge.scorer import score_event

    for missing in (
        "vol_ramp_entry_call", "vol_ramp_entry_put",
        "vol_ramp_exit_call", "vol_ramp_exit_put",
    ):
        s = score_event(prediction=_vr_pred(), context=_vr_ctx(**{missing: None}))
        assert s.evaluable is False
        assert s.not_evaluable_reason == "missing_vol_ramp_straddle"
        assert s.option_pnl is None


def test_score_directional_and_sell_vol_ignore_vol_ramp_fields() -> None:
    # NO-REGRESSION: a context WITH vol-ramp quotes must score identically for
    # the directional and sell-vol branches as one without them.
    from prescient.edge.scorer import score_event

    ctx_with = _vr_ctx()
    ctx_without = _vr_ctx(
        entry_as_of_date=None,
        vol_ramp_entry_call=None, vol_ramp_entry_put=None,
        vol_ramp_exit_call=None, vol_ramp_exit_put=None,
    )
    directional = _pred(PredictionDirection.UP)
    sell_vol = Prediction(
        ticker="MU", as_of_date=date(2024, 6, 25),
        direction=PredictionDirection.NONE, predicted_move_pct=0.0,
        confidence=0.5, source="short_vol", sell_straddle=True,
    )
    for pred in (directional, sell_vol):
        a = score_event(prediction=pred, context=ctx_with)
        b = score_event(prediction=pred, context=ctx_without)
        assert a == b


def test_directional_scoring_unchanged_no_regression() -> None:
    from datetime import date
    from prescient.edge.models import (
        EventContext, OptionQuote, Prediction, PredictionDirection, RealizedMove,
    )
    from prescient.edge.scorer import score_event

    def q(ot):
        return OptionQuote(ticker="MU", option_type=ot, strike=100.0,
                           expiration_date=date(2024, 7, 19),
                           quote_date=date(2024, 6, 25), bid=3.9, ask=4.1)
    ctx = EventContext(
        ticker="MU", earnings_date=date(2024, 6, 26), as_of_date=date(2024, 6, 25),
        underlying_price=100.0, atm_call=q("CALL"), atm_put=q("PUT"),
        realized_move=RealizedMove(ticker="MU", pre_report_close=100.0,
                                   post_report_close=112.0, realized_move_pct=12.0),
    )
    pred = Prediction(ticker="MU", as_of_date=date(2024, 6, 25),
                      direction=PredictionDirection.UP, predicted_move_pct=4.0,
                      confidence=0.55, source="reaction_aware_peer")
    s = score_event(prediction=pred, context=ctx)
    assert s.direction_correct is True
    assert s.beat_implied is True
    assert s.stayed_within_implied is None
