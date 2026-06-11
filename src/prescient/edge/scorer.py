from __future__ import annotations

from prescient.edge.implied_move import compute_implied_move
from prescient.edge.models import (
    EventContext,
    EventScore,
    Prediction,
    PredictionDirection,
)
from prescient.edge.option_pnl import (
    simulate_capped_short_straddle_pnl,
    simulate_option_pnl,
    simulate_vol_ramp_pnl,
)

_COST_HAIRCUT_PCT = 0.05
_DEFAULT_RISK_WIDTH_W = 5.0


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

    if prediction.buy_vol_ramp:
        # Strike-locked pre-event trade: buy the entry straddle, sell the SAME
        # contracts the day before earnings. Reads NO post-event price; the
        # implied/realized fields below are diagnostics only, never P&L inputs.
        legs = (
            context.vol_ramp_entry_call,
            context.vol_ramp_entry_put,
            context.vol_ramp_exit_call,
            context.vol_ramp_exit_put,
        )
        if any(leg is None or leg.bid is None for leg in legs):
            return EventScore(
                ticker=context.ticker,
                as_of_date=context.as_of_date,
                source=prediction.source,
                evaluable=False,
                not_evaluable_reason="missing_vol_ramp_straddle",
                confidence=prediction.confidence,
            )
        # History stamps bid == ask == close on these quotes.
        entry_premium = (
            context.vol_ramp_entry_call.bid + context.vol_ramp_entry_put.bid
        )
        exit_value = (
            context.vol_ramp_exit_call.bid + context.vol_ramp_exit_put.bid
        )
        vol_ramp_pnl = simulate_vol_ramp_pnl(
            entry_premium=entry_premium,
            exit_value=exit_value,
            cost_haircut_pct=_COST_HAIRCUT_PCT,
        )
        return EventScore(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            source=prediction.source,
            evaluable=vol_ramp_pnl is not None,
            not_evaluable_reason=(
                None if vol_ramp_pnl is not None else "invalid_vol_ramp_pnl"
            ),
            implied_move_pct=implied.implied_move_pct,
            realized_move_pct=realized_pct,
            option_pnl=vol_ramp_pnl,
            confidence=prediction.confidence,
        )

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

    stayed_within_implied: bool | None = None
    option_pnl = None
    strike = context.atm_call.strike if context.atm_call is not None else None

    if prediction.sell_straddle:
        # Non-directional defined-risk short straddle.
        stayed_within_implied = abs(realized_pct) < implied.implied_move_pct
        if strike is not None:
            option_pnl = simulate_capped_short_straddle_pnl(
                straddle_price=implied.straddle_price,
                strike=strike,
                underlying_price=context.underlying_price,
                post_report_close=realized.post_report_close,
                risk_width=_DEFAULT_RISK_WIDTH_W,
                cost_haircut_pct=_COST_HAIRCUT_PCT,
            )
    elif prediction.direction in (PredictionDirection.UP, PredictionDirection.DOWN):
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
        stayed_within_implied=stayed_within_implied,
    )
