from __future__ import annotations

from datetime import date

from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    EarningsCandidateDecision,
    OptionContractSnapshot,
    PeerScore,
    RejectionReason,
    StrategyStatus,
    TargetMarketData,
)
from prescient.signal.peer_scoring import aggregate_peer_scores
from prescient.signal.strategy_output import build_strategy_decision


def _candidate(
    *,
    status: CandidateDetectionStatus = CandidateDetectionStatus.CANDIDATE,
    theme: str | None = "AI_STORAGE",
    earnings_date: date | None = date(2026, 6, 2),
    reported_peers: list[str] | None = None,
    rejection_reasons: list[CandidateRejectionReason] | None = None,
) -> EarningsCandidateDecision:
    return EarningsCandidateDecision(
        target="NTNX",
        theme=theme,
        status=status,
        earnings_date=earnings_date,
        report_time="AMC",
        reported_peers=reported_peers or ["STX", "NTAP", "WDC", "PSTG"],
        rejection_reasons=rejection_reasons or [],
    )


def _strong_peer_scores() -> list[PeerScore]:
    return [
        PeerScore(
            ticker="NTAP",
            score=5,
            positive_factors=[
                "eps_beat",
                "revenue_beat",
                "positive_guidance",
                "positive_price_reaction",
                "positive_theme_driver",
            ],
        ),
        PeerScore(
            ticker="PSTG",
            score=4,
            positive_factors=[
                "eps_beat",
                "revenue_beat",
                "positive_guidance",
                "positive_theme_driver",
            ],
        ),
        PeerScore(
            ticker="WDC",
            score=3,
            positive_factors=[
                "eps_beat",
                "revenue_beat",
                "positive_theme_driver",
            ],
        ),
        PeerScore(
            ticker="STX",
            score=-1,
            negative_factors=["eps_miss"],
        ),
    ]


def _target_data(
    *,
    pre_earnings_runup_pct: float | None = 4.0,
) -> TargetMarketData:
    return TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=pre_earnings_runup_pct,
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


def test_builds_candidate_ready_for_analyst_with_structured_brief() -> None:
    scores = _strong_peer_scores()
    peer_signal = aggregate_peer_scores(scores)

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=peer_signal,
        target=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.rejection_reasons == []
    assert decision.candidate is not None
    assert decision.candidate.target == "NTNX"
    assert decision.candidate.theme == "AI_STORAGE"
    assert decision.candidate.earnings_date == date(2026, 6, 2)
    assert decision.candidate.report_time == "AMC"
    assert decision.candidate.direction == "bullish"
    assert decision.candidate.peer_signal_score == 2.75
    assert decision.candidate.positive_peer_ratio == 0.75
    assert decision.candidate.reported_peers == ["STX", "NTAP", "WDC", "PSTG"]
    assert decision.candidate.peer_scores == scores
    assert decision.candidate.recommended_expression == "CALL_OPTION"
    assert decision.candidate.strategy_status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.candidate.main_thesis == (
        "Bullish AI_STORAGE read-through for NTNX: 3 of 4 peers have positive "
        "earnings signal ahead of 2026-06-02 earnings."
    )
    assert decision.candidate.supporting_evidence == [
        "3 of 4 peers had positive scores.",
        "3 peers beat revenue estimates.",
        "2 peers showed positive guidance.",
        "3 peers confirmed theme-driver evidence.",
    ]
    assert decision.candidate.contradictions == ["1 peer had negative scores."]
    assert decision.candidate.model_dump(mode="json")["earnings_date"] == "2026-06-02"


def test_rejected_candidate_detection_becomes_no_trade_with_mapped_reasons() -> None:
    decision = build_strategy_decision(
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
        peer_signal=aggregate_peer_scores(_strong_peer_scores()),
        target=None,
        options_chain=[],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.candidate is None
    assert decision.rejection_reasons == [
        RejectionReason.THEME_NOT_CONFIGURED,
        RejectionReason.EARNINGS_DATE_UNCERTAIN,
        RejectionReason.INSUFFICIENT_PEERS_REPORTED,
    ]


def test_weak_peer_signal_becomes_no_trade() -> None:
    peer_signal = aggregate_peer_scores(
        [
            PeerScore(ticker="NTAP", score=1, positive_factors=["eps_beat"]),
            PeerScore(ticker="PSTG", score=-1, negative_factors=["eps_miss"]),
            PeerScore(ticker="WDC", score=0),
        ]
    )

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=peer_signal,
        target=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.candidate is None
    assert decision.rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]


def test_all_missing_peer_data_becomes_no_trade() -> None:
    peer_signal = aggregate_peer_scores(
        [
            PeerScore(
                ticker="NTAP",
                score=0,
                missing_factors=[
                    "eps_missing",
                    "revenue_missing",
                    "guidance_missing",
                    "price_reaction_missing",
                    "theme_driver_missing",
                ],
            ),
            PeerScore(
                ticker="PSTG",
                score=0,
                missing_factors=[
                    "eps_missing",
                    "revenue_missing",
                    "guidance_missing",
                    "price_reaction_missing",
                    "theme_driver_missing",
                ],
            ),
        ]
    )

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=peer_signal,
        target=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.candidate is None
    assert decision.rejection_reasons == [RejectionReason.MISSING_DATA]


def test_target_filter_rejection_reasons_are_propagated() -> None:
    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=aggregate_peer_scores(_strong_peer_scores()),
        target=_target_data(pre_earnings_runup_pct=12.5),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.candidate is None
    assert decision.rejection_reasons == [RejectionReason.TARGET_ALREADY_OVEREXTENDED]


def test_stock_fallback_is_reflected_in_candidate_brief() -> None:
    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=aggregate_peer_scores(_strong_peer_scores()),
        target=_target_data(),
        options_chain=[_call_option(bid=4.0, ask=6.0)],
    )

    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.candidate is not None
    assert decision.candidate.recommended_expression == "STOCK"
    assert decision.candidate.contradictions == [
        "1 peer had negative scores.",
        "Options liquidity failed; using stock fallback.",
    ]


def test_same_input_produces_equal_serialized_strategy_output() -> None:
    candidate = _candidate()
    peer_signal = aggregate_peer_scores(_strong_peer_scores())
    target = _target_data()
    options_chain = [_call_option()]

    first = build_strategy_decision(
        candidate=candidate,
        peer_signal=peer_signal,
        target=target,
        options_chain=options_chain,
    )
    second = build_strategy_decision(
        candidate=candidate,
        peer_signal=peer_signal,
        target=target,
        options_chain=options_chain,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
