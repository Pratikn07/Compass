from __future__ import annotations

from datetime import date

from prescient.signal.core import evaluate_core_strategy
from prescient.signal.models import (
    EarningsCalendarEvent,
    EarningsEvent,
    OptionContractSnapshot,
    PeerResult,
    RejectionReason,
    SignalValue,
    StrategySettings,
    StrategyStatus,
    StrategyUniverse,
    TargetMarketData,
    ThemeConfig,
)


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "NTAP", "PSTG", "WDC", "STX", "DELL"],
                drivers=["AI data center demand"],
            )
        ]
    )


def _upcoming_target(
    *,
    ticker: str = "NTNX",
    earnings_date: date | None = date(2026, 6, 2),
) -> EarningsCalendarEvent:
    return EarningsCalendarEvent(
        ticker=ticker,
        earnings_date=earnings_date,
        report_time="AMC",
    )


def _peer_result(
    ticker: str,
    *,
    earnings_date: date = date(2026, 5, 20),
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
            earnings_date=earnings_date,
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


def _negative_peer_result(ticker: str) -> PeerResult:
    return _peer_result(
        ticker,
        eps_actual=0.8,
        revenue_actual=900.0,
        price_reaction_pct=-4.0,
        guidance_signal="negative",
        theme_driver_signal="negative",
    )


def _missing_peer_result(ticker: str) -> PeerResult:
    return _peer_result(
        ticker,
        eps_estimate=None,
        eps_actual=None,
        revenue_estimate=None,
        revenue_actual=None,
        price_reaction_pct=None,
        guidance_signal="unknown",
        theme_driver_signal="unknown",
    )


def _target_data() -> TargetMarketData:
    return TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=4.0,
    )


def _call_option(
    *,
    bid: float | None = 4.85,
    ask: float | None = 5.15,
    open_interest: int | None = 250,
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        ticker="NTNX",
        option_type="CALL",
        expiration_date=date(2026, 6, 12),
        bid=bid,
        ask=ask,
        open_interest=open_interest,
    )


def test_five_ai_storage_peers_with_four_strong_results_create_bullish_candidate() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[
            _peer_result("NTAP"),
            _peer_result("PSTG"),
            _peer_result("WDC"),
            _peer_result("STX"),
            _negative_peer_result("DELL"),
        ],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.candidate is not None
    assert decision.candidate.target == "NTNX"
    assert decision.candidate.theme == "AI_STORAGE"
    assert decision.candidate.direction == "bullish"
    assert decision.candidate.recommended_expression == "CALL_OPTION"
    assert decision.candidate.positive_peer_ratio == 0.8
    assert decision.candidate.peer_signal_score == 3.0
    assert decision.candidate.reported_peers == ["NTAP", "PSTG", "WDC", "STX", "DELL"]
    assert decision.claude_analysis_allowed is True


def test_only_one_reported_peer_rejects_before_peer_scoring_thresholds() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[_peer_result("NTAP")],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.INSUFFICIENT_PEERS_REPORTED]
    assert decisions[0].candidate is None
    assert decisions[0].claude_analysis_allowed is False


def test_mixed_peer_results_reject_when_peer_signal_is_too_weak() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[
            _peer_result("NTAP"),
            _negative_peer_result("PSTG"),
            _negative_peer_result("WDC"),
        ],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]
    assert decisions[0].audit.peer_scores[0].ticker == "NTAP"


def test_all_missing_peer_earnings_data_rejects_with_missing_data() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[
            _missing_peer_result("NTAP"),
            _missing_peer_result("PSTG"),
            _missing_peer_result("WDC"),
        ],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option()]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.REJECTED_WITH_REASON
    assert decisions[0].rejection_reasons == [RejectionReason.MISSING_DATA]
    assert decisions[0].audit.all_peer_data_missing is True
    assert decisions[0].audit.missing_peer_factor_count == 15


def test_illiquid_options_do_not_produce_options_recommendation() -> None:
    decisions = evaluate_core_strategy(
        universe=_universe(),
        upcoming_events=[_upcoming_target()],
        peer_results=[
            _peer_result("NTAP"),
            _peer_result("PSTG"),
            _peer_result("WDC"),
        ],
        target_market_data={"NTNX": _target_data()},
        options_chains={"NTNX": [_call_option(bid=4.0, ask=6.0)]},
        current_date=date(2026, 6, 1),
    )

    assert decisions[0].status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decisions[0].candidate is not None
    assert decisions[0].candidate.recommended_expression == "STOCK"
    assert decisions[0].candidate.recommended_expression != "CALL_OPTION"


def test_same_end_to_end_input_produces_identical_serialized_output() -> None:
    universe = _universe()
    upcoming_events = [_upcoming_target()]
    peer_results = [
        _peer_result("NTAP"),
        _peer_result("PSTG"),
        _peer_result("WDC"),
    ]
    target_market_data = {"NTNX": _target_data()}
    options_chains = {"NTNX": [_call_option()]}
    current_date = date(2026, 6, 1)
    settings = StrategySettings()

    first = evaluate_core_strategy(
        universe=universe,
        upcoming_events=upcoming_events,
        peer_results=peer_results,
        target_market_data=target_market_data,
        options_chains=options_chains,
        current_date=current_date,
        settings=settings,
    )
    second = evaluate_core_strategy(
        universe=universe,
        upcoming_events=upcoming_events,
        peer_results=peer_results,
        target_market_data=target_market_data,
        options_chains=options_chains,
        current_date=current_date,
        settings=settings,
    )

    assert [decision.model_dump(mode="json") for decision in first] == [
        decision.model_dump(mode="json") for decision in second
    ]
