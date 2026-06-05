from __future__ import annotations

from prescient.edge.implied_move import compute_implied_move
from prescient.edge.models import (
    EventContext,
    EventScore,
    Prediction,
    PredictionDirection,
)
from prescient.edge.option_pnl import simulate_option_pnl

_COST_HAIRCUT_PCT = 0.05


def score_event(*, prediction: Prediction, context: EventContext) -> EventScore:
    realized = context.realized_move
    if realized is None:
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=False,
            not_evaluable_reason="missing_realized_move",
            confidence=prediction.confidence,
        )

    implied = compute_implied_move(
        ticker=context.ticker,
        as_of_date=context.as_of_date,
        underlying_price=context.underlying_price,
        atm_call=context.atm_call,
        atm_put=context.atm_put,
    )
    if implied is None:
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=False,
            not_evaluable_reason="missing_implied_move",
            confidence=prediction.confidence,
        )

    realized_pct = realized.realized_move_pct
    direction_correct: bool | None = None
    if prediction.direction == PredictionDirection.UP:
        direction_correct = realized_pct > 0
    elif prediction.direction == PredictionDirection.DOWN:
        direction_correct = realized_pct < 0

    beat_implied: bool | None = None
    if prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
        on_predicted_side = (
            realized_pct > 0
            if prediction.direction == PredictionDirection.UP
            else realized_pct < 0
        )
        beat_implied = on_predicted_side and (
            abs(realized_pct) >= implied.implied_move_pct
        )

    option_pnl = None
    if prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
        strike = context.atm_call.strike if context.atm_call is not None else None
        if strike is not None:
            option_pnl = simulate_option_pnl(
                direction=prediction.direction.name,  # "UP"/"DOWN"
                strike=strike,
                entry_premium=implied.straddle_price / 2.0,
                post_report_close=realized.post_report_close,
                cost_haircut_pct=_COST_HAIRCUT_PCT,
            )

    return EventScore(
        ticker=context.ticker,
        as_of_date=context.as_of_date,
        source=prediction.source,
        evaluable=True,
        direction_correct=direction_correct,
        beat_implied=beat_implied,
        implied_move_pct=implied.implied_move_pct,
        realized_move_pct=realized_pct,
        option_pnl=option_pnl,
        confidence=prediction.confidence,
    )
