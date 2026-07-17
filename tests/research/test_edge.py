from __future__ import annotations

from datetime import date, timedelta

from compass.research.edge.loader import PointInTimeDataset, build_event_context
from compass.research.edge.models import (
    DailyBar,
    EventContext,
    OptionQuote,
    Prediction,
    PredictionDirection,
    RealizedMove,
)
from compass.research.edge.runner import run_edge_backtest
from compass.research.edge.strategy import (
    AlwaysUpStrategy,
    CoinFlipStrategy,
    ReactionAwarePeerStrategy,
)


def quote(option_type: str, quote_date: date) -> OptionQuote:
    return OptionQuote(
        ticker="MU",
        option_type=option_type,
        strike=100.0,
        expiration_date=date(2026, 8, 21),
        quote_date=quote_date,
        bid=3.9,
        ask=4.1,
    )


def context(as_of: date, realized_pct: float) -> EventContext:
    return EventContext(
        ticker="MU",
        earnings_date=as_of + timedelta(days=1),
        as_of_date=as_of,
        underlying_price=100.0,
        atm_call=quote("CALL", as_of),
        atm_put=quote("PUT", as_of),
        peer_eps_surprises={"NVDA": 5.0},
        peer_stock_reactions={"NVDA": 2.0},
        realized_move=RealizedMove(
            ticker="MU",
            pre_report_close=100.0,
            post_report_close=100.0 * (1 + realized_pct / 100),
            realized_move_pct=realized_pct,
        ),
    )


def test_point_in_time_dataset_never_exposes_future_rows() -> None:
    dataset = PointInTimeDataset(
        bars={
            "MU": [
                DailyBar(ticker="MU", trading_date=date(2026, 7, 15), close=100),
                DailyBar(ticker="MU", trading_date=date(2026, 7, 17), close=106),
            ]
        },
        option_quotes={
            "MU": [quote("CALL", date(2026, 7, 15)), quote("PUT", date(2026, 7, 17))]
        },
    )

    bars = dataset.bars_as_of("MU", as_of_date=date(2026, 7, 15))
    quotes = dataset.option_quotes_as_of("MU", as_of_date=date(2026, 7, 15))

    assert [bar.trading_date for bar in bars] == [date(2026, 7, 15)]
    assert [row.quote_date for row in quotes] == [date(2026, 7, 15)]


def test_event_context_reads_inputs_as_of_but_scores_future_outcome() -> None:
    dataset = PointInTimeDataset(
        bars={
            "MU": [
                DailyBar(ticker="MU", trading_date=date(2026, 7, 14), close=99),
                DailyBar(ticker="MU", trading_date=date(2026, 7, 15), close=100),
                DailyBar(ticker="MU", trading_date=date(2026, 7, 16), close=103),
                DailyBar(ticker="MU", trading_date=date(2026, 7, 17), close=106),
            ]
        },
        option_quotes={
            "MU": [quote("CALL", date(2026, 7, 15)), quote("PUT", date(2026, 7, 15))]
        },
    )

    result = build_event_context(
        dataset=dataset,
        ticker="MU",
        earnings_date=date(2026, 7, 16),
        as_of_date=date(2026, 7, 15),
        horizon_days=2,
    )

    assert result is not None
    assert result.underlying_price == 100
    assert result.realized_move is not None
    assert result.realized_move.realized_move_pct == 6


def test_edge_runner_preserves_baselines_and_sample_size_guard() -> None:
    result = run_edge_backtest(
        contexts=[context(date(2026, 7, 15), 6.0)],
        strategies=[ReactionAwarePeerStrategy(), CoinFlipStrategy(), AlwaysUpStrategy()],
    )

    assert set(result.scorecards) == {
        "reaction_aware_peer",
        "coin_flip",
        "always_up",
    }
    assert result.scorecards["reaction_aware_peer"].survived is False


def test_edge_runner_can_survive_only_with_positive_return_and_enough_events() -> None:
    class StrongUp:
        source = "reaction_aware_peer"

        def predict(self, event: EventContext) -> Prediction:
            return Prediction(
                ticker=event.ticker,
                as_of_date=event.as_of_date,
                direction=PredictionDirection.UP,
                predicted_move_pct=12,
                confidence=0.8,
                source=self.source,
            )

    class DownBaseline:
        source = "coin_flip"

        def predict(self, event: EventContext) -> Prediction:
            return Prediction(
                ticker=event.ticker,
                as_of_date=event.as_of_date,
                direction=PredictionDirection.DOWN,
                predicted_move_pct=0,
                confidence=0.5,
                source=self.source,
            )

    class NoTradeBaseline:
        source = "always_up"

        def predict(self, event: EventContext) -> Prediction:
            return Prediction(
                ticker=event.ticker,
                as_of_date=event.as_of_date,
                direction=PredictionDirection.NONE,
                predicted_move_pct=0,
                confidence=0.5,
                source=self.source,
            )

    events = [context(date(2025, 1, 1) + timedelta(days=index), 12) for index in range(200)]
    result = run_edge_backtest(
        contexts=events,
        strategies=[StrongUp(), DownBaseline(), NoTradeBaseline()],
    )

    assert result.scorecards["reaction_aware_peer"].survived is True
