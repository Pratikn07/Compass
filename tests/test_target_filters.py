from __future__ import annotations

from datetime import date

from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    EarningsCandidateDecision,
    OptionContractSnapshot,
    PeerSignal,
    RejectionReason,
    StrategySettings,
    TargetFilterStatus,
    TargetMarketData,
)
from prescient.signal.target_filters import run_target_filters


def _candidate(
    *,
    status: CandidateDetectionStatus = CandidateDetectionStatus.CANDIDATE,
    theme: str | None = "AI_STORAGE",
    earnings_date: date | None = date(2026, 6, 2),
    rejection_reasons: list[CandidateRejectionReason] | None = None,
) -> EarningsCandidateDecision:
    return EarningsCandidateDecision(
        target="NTNX",
        theme=theme,
        status=status,
        earnings_date=earnings_date,
        report_time="AMC",
        reported_peers=["NTAP", "PSTG", "WDC"],
        rejection_reasons=rejection_reasons or [],
    )


def _passing_peer_signal() -> PeerSignal:
    return PeerSignal(
        peer_scores=[],
        average_peer_score=3.2,
        positive_peer_count=3,
        negative_peer_count=0,
        positive_peer_ratio=1.0,
        missing_data_count=0,
        passes_thresholds=True,
    )


def _weak_peer_signal() -> PeerSignal:
    return PeerSignal(
        peer_scores=[],
        average_peer_score=1.5,
        positive_peer_count=1,
        negative_peer_count=2,
        positive_peer_ratio=1 / 3,
        missing_data_count=0,
        passes_thresholds=False,
    )


def _target_data(
    *,
    avg_daily_volume: int | None = 2_000_000,
    pre_earnings_runup_pct: float | None = 4.0,
    has_conflicting_news: bool = False,
    has_invalidating_event: bool = False,
    is_extremely_illiquid: bool = False,
) -> TargetMarketData:
    return TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=avg_daily_volume,
        pre_earnings_runup_pct=pre_earnings_runup_pct,
        has_conflicting_news=has_conflicting_news,
        has_invalidating_event=has_invalidating_event,
        is_extremely_illiquid=is_extremely_illiquid,
    )


def _call_option(
    *,
    expiration_date: date = date(2026, 6, 12),
    bid: float | None = 4.85,
    ask: float | None = 5.15,
    open_interest: int | None = 250,
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        ticker="NTNX",
        option_type="CALL",
        expiration_date=expiration_date,
        bid=bid,
        ask=ask,
        open_interest=open_interest,
    )


def test_passes_with_valid_candidate_liquid_target_and_liquid_call_option() -> None:
    option = _call_option()

    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        options_chain=[option],
    )

    assert decision.status == TargetFilterStatus.PASSED
    assert decision.target == "NTNX"
    assert decision.theme == "AI_STORAGE"
    assert decision.recommended_expression == "CALL_OPTION"
    assert decision.selected_option == option
    assert decision.rejection_reasons == []
    assert decision.warnings == []


def test_falls_back_to_stock_when_options_fail_and_fallback_is_enabled() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        options_chain=[_call_option(bid=4.0, ask=6.0)],
    )

    assert decision.status == TargetFilterStatus.PASSED
    assert decision.recommended_expression == "STOCK"
    assert decision.selected_option is None
    assert decision.rejection_reasons == []
    assert decision.warnings == [RejectionReason.OPTIONS_TOO_ILLIQUID]


def test_rejects_options_failure_when_stock_fallback_is_disabled() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        options_chain=[_call_option(open_interest=25)],
        settings=StrategySettings(allow_stock_fallback=False),
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.recommended_expression == "NONE"
    assert decision.selected_option is None
    assert decision.rejection_reasons == [RejectionReason.OPTIONS_TOO_ILLIQUID]
    assert decision.warnings == []


def test_stock_expression_bypasses_options_checks() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        preferred_expression="STOCK",
        options_chain=[],
    )

    assert decision.status == TargetFilterStatus.PASSED
    assert decision.recommended_expression == "STOCK"
    assert decision.selected_option is None
    assert decision.rejection_reasons == []
    assert decision.warnings == []


def test_rejects_low_volume_and_extreme_illiquidity() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(avg_daily_volume=500_000, is_extremely_illiquid=True),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.recommended_expression == "NONE"
    assert decision.rejection_reasons == [RejectionReason.TARGET_TOO_ILLIQUID]


def test_rejects_overextended_target() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(pre_earnings_runup_pct=12.5),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.rejection_reasons == [RejectionReason.TARGET_ALREADY_OVEREXTENDED]


def test_rejects_conflicting_news() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(has_conflicting_news=True),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.rejection_reasons == [RejectionReason.CONFLICTING_NEWS]


def test_rejects_invalidating_event() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(has_invalidating_event=True),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.rejection_reasons == [
        RejectionReason.TARGET_EVENT_INVALIDATES_PEER_COMPARISON
    ]


def test_rejects_missing_target_market_data() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(avg_daily_volume=None, pre_earnings_runup_pct=None),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.rejection_reasons == [RejectionReason.MISSING_DATA]


def test_rejects_weak_peer_signal_before_market_checks() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_weak_peer_signal(),
        target_data=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]


def test_maps_rejected_candidate_prerequisites_to_prd_rejection_reasons() -> None:
    decision = run_target_filters(
        candidate=_candidate(
            status=CandidateDetectionStatus.REJECTED,
            theme=None,
            earnings_date=None,
            rejection_reasons=[
                CandidateRejectionReason.THEME_NOT_CONFIGURED,
                CandidateRejectionReason.EARNINGS_DATE_MISSING,
                CandidateRejectionReason.INSUFFICIENT_REPORTED_PEERS,
            ],
        ),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == TargetFilterStatus.REJECTED
    assert decision.theme is None
    assert decision.rejection_reasons == [
        RejectionReason.THEME_NOT_CONFIGURED,
        RejectionReason.EARNINGS_DATE_UNCERTAIN,
        RejectionReason.INSUFFICIENT_PEERS_REPORTED,
    ]


def test_ignores_options_expiring_too_late_for_earnings_window() -> None:
    decision = run_target_filters(
        candidate=_candidate(),
        peer_signal=_passing_peer_signal(),
        target_data=_target_data(),
        options_chain=[_call_option(expiration_date=date(2026, 7, 17))],
    )

    assert decision.status == TargetFilterStatus.PASSED
    assert decision.recommended_expression == "STOCK"
    assert decision.selected_option is None
    assert decision.warnings == [RejectionReason.OPTIONS_TOO_ILLIQUID]


def test_produces_identical_serialized_output_for_identical_input() -> None:
    candidate = _candidate()
    peer_signal = _passing_peer_signal()
    target_data = _target_data()
    options_chain = [_call_option()]

    first = run_target_filters(
        candidate=candidate,
        peer_signal=peer_signal,
        target_data=target_data,
        options_chain=options_chain,
    )
    second = run_target_filters(
        candidate=candidate,
        peer_signal=peer_signal,
        target_data=target_data,
        options_chain=options_chain,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
