from __future__ import annotations

from datetime import date

from prescient.edge.models import (
    EventContext,
    OptionQuote,
    RealizedMove,
)


def _quote(ot):
    return OptionQuote(
        ticker="MU", option_type=ot, strike=100.0,
        expiration_date=date(2024, 7, 19), quote_date=date(2024, 6, 25),
        bid=3.9, ask=4.1,
    )


def _ctx(ticker, realized_pct, as_of):
    return EventContext(
        ticker=ticker, earnings_date=date(2024, 6, 26), as_of_date=as_of,
        underlying_price=100.0, atm_call=_quote("CALL"), atm_put=_quote("PUT"),
        peer_eps_surprises={"X": 5.0}, peer_stock_reactions={"X": 1.0},
        realized_move=RealizedMove(
            ticker=ticker, pre_report_close=100.0,
            post_report_close=100.0 * (1 + realized_pct / 100.0),
            realized_move_pct=realized_pct,
        ),
    )


def test_runner_produces_one_scorecard_per_strategy() -> None:
    from prescient.edge.runner import run_edge_backtest
    from prescient.edge.strategy import (
        AlwaysUpStrategy,
        CoinFlipStrategy,
        ReactionAwarePeerStrategy,
    )

    contexts = [
        _ctx("MU", 6.0, date(2024, 6, 25)),
        _ctx("NVDA", -4.0, date(2024, 5, 20)),
    ]
    result = run_edge_backtest(
        contexts=contexts,
        strategies=[
            ReactionAwarePeerStrategy(),
            CoinFlipStrategy(),
            AlwaysUpStrategy(),
        ],
    )
    assert set(result.scorecards.keys()) == {
        "reaction_aware_peer", "coin_flip", "always_up",
    }
    # too few events -> not survived regardless of rates
    assert result.scorecards["reaction_aware_peer"].survived is False


def test_runner_marks_survived_when_beats_both_baselines_with_enough_events() -> None:
    from datetime import timedelta

    from prescient.edge.models import Prediction, PredictionDirection
    from prescient.edge.runner import run_edge_backtest

    # Synthetic strategies with fixed behavior. The "reaction_aware_peer" strategy
    # always predicts a big UP; baselines predict in ways that beat implied less often.
    class AlwaysUpBeats:
        source = "reaction_aware_peer"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.UP, predicted_move_pct=10.0,
                confidence=0.8, source=self.source,
            )

    class FlipDown:
        source = "coin_flip"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.DOWN, predicted_move_pct=0.0,
                confidence=0.5, source=self.source,
            )

    class NoTrade:
        source = "always_up"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.NONE, predicted_move_pct=0.0,
                confidence=0.5, source=self.source,
            )

    # 200 events, all big UP moves (+12% > implied 8%): reaction_aware_peer beats
    # implied every time (100%); FlipDown predicts DOWN so never beats on the up move
    # (0%); NoTrade predicts NONE so beat_implied is None (no beat-implied data -> rate
    # None, treated as 0 by the runner's baseline max). Strategy clears both baselines
    # with MODERATE sample size -> survived True.
    contexts = [
        _ctx("MU", 12.0, date(2024, 1, 1) + timedelta(days=i))
        for i in range(200)
    ]
    result = run_edge_backtest(
        contexts=contexts,
        strategies=[AlwaysUpBeats(), FlipDown(), NoTrade()],
    )
    card = result.scorecards["reaction_aware_peer"]
    assert card.beat_implied_rate == 100.0
    assert card.survived is True


def test_runner_rejects_duplicate_strategy_sources() -> None:
    import pytest

    from prescient.edge.models import Prediction, PredictionDirection
    from prescient.edge.runner import run_edge_backtest

    class DupA:
        source = "reaction_aware_peer"
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.UP, predicted_move_pct=1.0,
                confidence=0.5, source=self.source,
            )

    class DupB:
        source = "reaction_aware_peer"  # same source -> must be rejected
        def predict(self, context):
            return Prediction(
                ticker=context.ticker, as_of_date=context.as_of_date,
                direction=PredictionDirection.DOWN, predicted_move_pct=1.0,
                confidence=0.5, source=self.source,
            )

    with pytest.raises(ValueError, match="Duplicate strategy source"):
        run_edge_backtest(
            contexts=[_ctx("MU", 6.0, date(2024, 6, 25))],
            strategies=[DupA(), DupB()],
        )
