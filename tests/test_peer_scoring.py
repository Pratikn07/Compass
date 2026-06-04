from __future__ import annotations

from datetime import date

from prescient.signal.models import EarningsEvent, PeerResult, SignalValue, StrategySettings
from prescient.signal.peer_scoring import aggregate_peer_scores, score_peer_result


def _peer(
    ticker: str = "NTAP",
    *,
    eps_estimate: float | None = 1.0,
    eps_actual: float | None = 1.2,
    revenue_estimate: float | None = 1_000.0,
    revenue_actual: float | None = 1_100.0,
    price_reaction_pct: float | None = 4.0,
    guidance_signal: SignalValue = "positive",
    theme_driver_signal: SignalValue = "positive",
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2026, 5, 20),
            report_time="AMC",
            eps_estimate=eps_estimate,
            eps_actual=eps_actual,
            revenue_estimate=revenue_estimate,
            revenue_actual=revenue_actual,
        ),
        price_reaction_pct=price_reaction_pct,
        guidance_signal=guidance_signal,
        theme_driver_signal=theme_driver_signal,
    )


def test_fully_positive_peer_result_scores_five() -> None:
    score = score_peer_result(_peer())

    assert score.ticker == "NTAP"
    assert score.score == 5
    assert score.positive_factors == [
        "eps_beat",
        "revenue_beat",
        "positive_guidance",
        "positive_price_reaction",
        "positive_theme_driver",
    ]
    assert score.negative_factors == []
    assert score.missing_factors == []


def test_fully_negative_peer_result_scores_negative_five() -> None:
    score = score_peer_result(
        _peer(
            eps_actual=0.8,
            revenue_actual=900.0,
            price_reaction_pct=-4.0,
            guidance_signal="negative",
            theme_driver_signal="negative",
        )
    )

    assert score.score == -5
    assert score.positive_factors == []
    assert score.negative_factors == [
        "eps_miss",
        "revenue_miss",
        "negative_guidance",
        "negative_price_reaction",
        "negative_theme_driver",
    ]
    assert score.missing_factors == []


def test_missing_structured_inputs_are_recorded_without_changing_score() -> None:
    score = score_peer_result(
        _peer(
            eps_estimate=None,
            eps_actual=None,
            revenue_estimate=None,
            revenue_actual=None,
            price_reaction_pct=None,
            guidance_signal="unknown",
            theme_driver_signal="unknown",
        )
    )

    assert score.score == 0
    assert score.positive_factors == []
    assert score.negative_factors == []
    assert score.missing_factors == [
        "eps_missing",
        "revenue_missing",
        "guidance_missing",
        "price_reaction_missing",
        "theme_driver_missing",
    ]


def test_neutral_guidance_and_theme_driver_do_not_change_score_or_missing_factors() -> None:
    score = score_peer_result(
        _peer(
            eps_actual=1.0,
            revenue_actual=1_000.0,
            price_reaction_pct=0.0,
            guidance_signal="neutral",
            theme_driver_signal="neutral",
        )
    )

    assert score.score == 0
    assert score.positive_factors == []
    assert score.negative_factors == []
    assert score.missing_factors == []


def test_price_reaction_thresholds_are_inclusive() -> None:
    positive_score = score_peer_result(
        _peer(
            eps_actual=1.0,
            revenue_actual=1_000.0,
            price_reaction_pct=3.0,
            guidance_signal="neutral",
            theme_driver_signal="neutral",
        )
    )
    negative_score = score_peer_result(
        _peer(
            eps_actual=1.0,
            revenue_actual=1_000.0,
            price_reaction_pct=-3.0,
            guidance_signal="neutral",
            theme_driver_signal="neutral",
        )
    )

    assert positive_score.score == 1
    assert positive_score.positive_factors == ["positive_price_reaction"]
    assert negative_score.score == -1
    assert negative_score.negative_factors == ["negative_price_reaction"]


def test_custom_strategy_settings_change_price_and_aggregate_thresholds() -> None:
    settings = StrategySettings(
        positive_price_reaction_pct=5.0,
        negative_price_reaction_pct=-5.0,
        min_positive_peer_ratio=0.5,
        min_average_peer_score=1.0,
    )

    positive_score = score_peer_result(
        _peer(guidance_signal="neutral", theme_driver_signal="neutral"),
        settings=settings,
    )
    negative_score = score_peer_result(
        _peer(
            ticker="PSTG",
            eps_actual=0.8,
            revenue_actual=900.0,
            price_reaction_pct=-4.0,
            guidance_signal="neutral",
            theme_driver_signal="neutral",
        ),
        settings=settings,
    )
    signal = aggregate_peer_scores([positive_score, negative_score], settings=settings)

    assert positive_score.score == 2
    assert "positive_price_reaction" not in positive_score.positive_factors
    assert negative_score.score == -2
    assert "negative_price_reaction" not in negative_score.negative_factors
    assert signal.positive_peer_ratio == 0.5
    assert signal.average_peer_score == 0.0
    assert signal.passes_thresholds is False


def test_aggregate_peer_scores_calculates_peer_signal_metrics() -> None:
    scores = [
        score_peer_result(_peer(ticker="NTAP")),
        score_peer_result(
            _peer(
                ticker="PSTG",
                eps_actual=0.8,
                revenue_actual=900.0,
                price_reaction_pct=-4.0,
                guidance_signal="negative",
                theme_driver_signal="negative",
            )
        ),
        score_peer_result(
            _peer(
                ticker="WDC",
                eps_estimate=None,
                eps_actual=None,
                revenue_estimate=None,
                revenue_actual=None,
                price_reaction_pct=None,
                guidance_signal="unknown",
                theme_driver_signal="unknown",
            )
        ),
    ]

    signal = aggregate_peer_scores(scores)

    assert signal.peer_scores == scores
    assert signal.average_peer_score == 0.0
    assert signal.positive_peer_count == 1
    assert signal.negative_peer_count == 1
    assert signal.positive_peer_ratio == 1 / 3
    assert signal.missing_data_count == 5
    assert signal.passes_thresholds is False


def test_aggregate_peer_scores_passes_when_ratio_and_average_clear_defaults() -> None:
    scores = [
        score_peer_result(_peer(ticker="NTAP")),
        score_peer_result(_peer(ticker="PSTG")),
        score_peer_result(_peer(ticker="WDC")),
        score_peer_result(
            _peer(
                ticker="STX",
                eps_actual=0.8,
                revenue_actual=900.0,
                price_reaction_pct=-4.0,
                guidance_signal="negative",
                theme_driver_signal="negative",
            )
        ),
    ]

    signal = aggregate_peer_scores(scores)

    assert signal.average_peer_score == 2.5
    assert signal.positive_peer_count == 3
    assert signal.negative_peer_count == 1
    assert signal.positive_peer_ratio == 0.75
    assert signal.missing_data_count == 0
    assert signal.passes_thresholds is True


def test_empty_aggregate_returns_zero_metrics_and_fails_thresholds() -> None:
    signal = aggregate_peer_scores([])

    assert signal.peer_scores == []
    assert signal.average_peer_score == 0.0
    assert signal.positive_peer_count == 0
    assert signal.negative_peer_count == 0
    assert signal.positive_peer_ratio == 0.0
    assert signal.missing_data_count == 0
    assert signal.passes_thresholds is False
