from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    DecisionAudit,
    EarningsCandidateDecision,
    OptionContractSnapshot,
    PeerScore,
    RejectionReason,
    RejectionStage,
    StrategyDecision,
    StrategyStatus,
    TargetMarketData,
)
from prescient.signal.peer_scoring import aggregate_peer_scores
from prescient.signal.rejections import build_rejection_details
from prescient.signal.strategy_output import build_strategy_decision


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
        reported_peers=["NTAP", "PSTG", "WDC", "STX"],
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
        PeerScore(ticker="STX", score=-1, negative_factors=["eps_miss"]),
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


def _audit() -> DecisionAudit:
    return DecisionAudit(
        target="NTNX",
        theme="AI_STORAGE",
        peer_scores=[],
        thresholds={
            "min_positive_peer_ratio": 0.67,
            "min_average_peer_score": 2.0,
            "min_avg_daily_volume": 1_000_000,
            "max_target_runup_pct": 10.0,
            "allow_stock_fallback": True,
        },
        missing_peer_factor_count=0,
        all_peer_data_missing=False,
        target_market_data_present=True,
        option_contract_count=1,
    )


def test_rejected_candidate_detection_has_clear_details_and_blocks_claude() -> None:
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
    assert decision.claude_analysis_allowed is False
    assert decision.rejection_reasons == [
        RejectionReason.THEME_NOT_CONFIGURED,
        RejectionReason.EARNINGS_DATE_UNCERTAIN,
        RejectionReason.INSUFFICIENT_PEERS_REPORTED,
    ]
    assert [detail.stage for detail in decision.rejection_details] == [
        RejectionStage.CANDIDATE_DETECTION,
        RejectionStage.CANDIDATE_DETECTION,
        RejectionStage.CANDIDATE_DETECTION,
    ]
    assert [detail.message for detail in decision.rejection_details] == [
        "Target is not in a configured strategy theme.",
        "Target earnings date is missing or outside the allowed earnings window.",
        "Not enough same-theme peers have reported in the required window.",
    ]
    assert decision.audit.target == "NTNX"
    assert decision.audit.theme is None
    assert decision.audit.target_market_data_present is False
    assert decision.audit.option_contract_count == 0


def test_weak_peer_signal_rejects_at_peer_signal_stage() -> None:
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
    assert decision.rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]
    assert decision.rejection_details[0].stage == RejectionStage.PEER_SIGNAL
    assert decision.rejection_details[0].message == (
        "Reported peer signal does not meet the minimum ratio or average score thresholds."
    )


def test_all_missing_peer_data_rejects_and_marks_audit() -> None:
    missing_scores = [
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

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=aggregate_peer_scores(missing_scores),
        target=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.rejection_reasons == [RejectionReason.MISSING_DATA]
    assert decision.rejection_details[0].stage == RejectionStage.PEER_SIGNAL
    assert decision.audit.all_peer_data_missing is True
    assert decision.audit.missing_peer_factor_count == 10


def test_target_filter_rejection_contains_journal_safe_audit() -> None:
    peer_signal = aggregate_peer_scores(_strong_peer_scores())

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=peer_signal,
        target=_target_data(pre_earnings_runup_pct=12.5),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.REJECTED_WITH_REASON
    assert decision.rejection_reasons == [RejectionReason.TARGET_ALREADY_OVEREXTENDED]
    assert decision.rejection_details[0].stage == RejectionStage.TARGET_FILTER
    assert decision.audit.target == "NTNX"
    assert decision.audit.theme == "AI_STORAGE"
    assert decision.audit.peer_scores == peer_signal.peer_scores
    assert decision.audit.thresholds == {
        "min_positive_peer_ratio": 0.67,
        "min_average_peer_score": 2.0,
        "min_avg_daily_volume": 1_000_000,
        "max_target_runup_pct": 10.0,
        "allow_stock_fallback": True,
    }
    assert decision.audit.target_market_data_present is True
    assert decision.audit.option_contract_count == 1


def test_rejection_details_deduplicate_reasons_and_preserve_order() -> None:
    details = build_rejection_details(
        reasons=[
            RejectionReason.PEER_SIGNAL_TOO_WEAK,
            RejectionReason.MISSING_DATA,
            RejectionReason.PEER_SIGNAL_TOO_WEAK,
        ],
        stage=RejectionStage.PEER_SIGNAL,
    )

    assert [detail.reason for detail in details] == [
        RejectionReason.PEER_SIGNAL_TOO_WEAK,
        RejectionReason.MISSING_DATA,
    ]
    assert [detail.message for detail in details] == [
        "Reported peer signal does not meet the minimum ratio or average score thresholds.",
        "Required structured data is missing and must not be guessed.",
    ]


def test_candidate_ready_has_no_rejections_and_allows_claude() -> None:
    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=aggregate_peer_scores(_strong_peer_scores()),
        target=_target_data(),
        options_chain=[_call_option()],
    )

    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.candidate is not None
    assert decision.rejection_reasons == []
    assert decision.rejection_details == []
    assert decision.claude_analysis_allowed is True
    assert decision.audit.target == "NTNX"


def test_strategy_decision_rejects_rejected_status_without_reasons_or_details() -> None:
    with pytest.raises(ValidationError):
        StrategyDecision(
            status=StrategyStatus.REJECTED_WITH_REASON,
            candidate=None,
            rejection_reasons=[],
            rejection_details=[],
            audit=_audit(),
            claude_analysis_allowed=False,
        )


def test_same_rejected_input_produces_equal_serialized_output() -> None:
    candidate = _candidate()
    peer_signal = aggregate_peer_scores(_strong_peer_scores())
    target = _target_data(pre_earnings_runup_pct=12.5)
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


def test_serialized_rejection_output_contains_journal_fields() -> None:
    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=aggregate_peer_scores(_strong_peer_scores()),
        target=_target_data(pre_earnings_runup_pct=12.5),
        options_chain=[_call_option()],
    )

    serialized = decision.model_dump(mode="json")

    assert serialized["status"] == "rejected_with_reason"
    assert serialized["candidate"] is None
    assert serialized["rejection_reasons"] == ["target_already_overextended"]
    assert serialized["rejection_details"][0] == {
        "reason": "target_already_overextended",
        "stage": "target_filter",
        "message": (
            "Target has already moved beyond the allowed pre-earnings run-up threshold."
        ),
    }
    assert serialized["audit"]["target"] == "NTNX"
    assert serialized["audit"]["theme"] == "AI_STORAGE"
    assert serialized["audit"]["peer_scores"]
    assert serialized["audit"]["thresholds"]["min_positive_peer_ratio"] == 0.67
    assert serialized["audit"]["missing_peer_factor_count"] == 0
    assert serialized["audit"]["all_peer_data_missing"] is False
