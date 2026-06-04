from __future__ import annotations

from datetime import date

from prescient.journal import DecisionLayer, DecisionType, SourceCitation, internal_rule_citation
from prescient.signal import (
    CandidateDetectionStatus,
    EarningsCalendarEvent,
    EarningsCandidateDecision,
    EarningsEvent,
    IndicatorFreshness,
    MacdState,
    OptionContractSnapshot,
    PeerResult,
    PeerScore,
    PriceVsVwapState,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
    build_strategy_decision,
    aggregate_peer_scores,
    score_peer_result,
    StrategyStatus,
    RejectionReason,
)


def _citation(citation_id: str, source_type: str) -> SourceCitation:
    return SourceCitation(
        citation_id=citation_id,
        provider="fixture",
        source_type=source_type,
        title=source_type,
        excerpt="bounded evidence",
    )


def _candidate() -> EarningsCandidateDecision:
    return EarningsCandidateDecision(
        status=CandidateDetectionStatus.CANDIDATE_FOUND,
        target="NTNX",
        theme="AI_STORAGE",
        earnings_date=date(2026, 6, 10),
        report_time="AMC",
        reported_peers=["NTAP", "PSTG", "WDC"],
        upcoming_event=EarningsCalendarEvent(
                ticker="NTNX",
                earnings_date=date(2026, 6, 10),
                report_time="AMC",
            source_citations=[_citation("target-calendar", "earnings_calendar")],
        ),
    )


def _peer_result(ticker: str, citation_id: str) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2026, 6, 1),
            report_time="AMC",
            eps_estimate=1.0,
            eps_actual=1.2,
            revenue_estimate=100.0,
            revenue_actual=110.0,
            source_citations=[_citation(f"{citation_id}-earnings", "earnings_result")],
        ),
        price_reaction_pct=4.0,
        guidance_signal="positive",
        theme_driver_signal="positive",
        source_urls=[f"https://example.test/{ticker.lower()}"],
        source_citations=[_citation(citation_id, "peer_result")],
    )


def test_candidate_ready_decision_carries_source_and_rule_citations() -> None:
    peer_results = [
        _peer_result("NTAP", "peer-ntap"),
        _peer_result("PSTG", "peer-pstg"),
        _peer_result("WDC", "peer-wdc"),
    ]
    peer_signal = aggregate_peer_scores([score_peer_result(peer) for peer in peer_results])
    target = TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=4.0,
        source_citations=[_citation("target-market", "market_data")],
    )
    options = [
        OptionContractSnapshot(
            ticker="NTNX",
            option_type="CALL",
            expiration_date=date(2026, 6, 20),
            bid=1.0,
            ask=1.1,
            open_interest=500,
            source_citations=[_citation("option-chain", "options_chain")],
        )
    ]
    indicators = TechnicalIndicatorSnapshot(
        ticker="NTNX",
        as_of=date(2026, 6, 2),
        rsi_14=55.0,
        macd_line=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        macd_state=MacdState.BULLISH,
        vwap=20.0,
        price_vs_vwap=PriceVsVwapState.ABOVE,
        missing_fields=[],
        source="alpha_vantage",
        freshness=IndicatorFreshness.CURRENT,
        source_citations=[_citation("indicator", "technical_indicators")],
    )

    decision = build_strategy_decision(
        candidate=_candidate(),
        peer_signal=peer_signal,
        target=target,
        indicator_snapshot=indicators,
        options_chain=options,
    )

    citation_ids = {c.citation_id for c in decision.audit_trail.source_citations}
    assert decision.status == StrategyStatus.CANDIDATE_READY_FOR_ANALYST
    assert decision.audit_trail.decision_layer == DecisionLayer.SIGNAL
    assert decision.audit_trail.decision_type == DecisionType.STRATEGY_DECISION
    assert decision.candidate is not None
    assert {c.citation_id for c in decision.candidate.source_citations} <= citation_ids
    assert {
        "target-calendar",
        "peer-ntap",
        "peer-ntap-earnings",
        "target-market",
        "option-chain",
        "indicator",
    } <= citation_ids
    assert any(f.rule_name == "min_positive_peer_ratio" for f in decision.audit_trail.rule_facts)
    assert any(c.source_type == "strategy_rule" for c in decision.audit_trail.source_citations)


def test_rejected_decision_includes_failed_rule_fact_and_citations() -> None:
    weak_signal = aggregate_peer_scores(
        [
            PeerScore(
                ticker="NTAP",
                score=1,
                positive_factors=["eps_beat"],
                negative_factors=[],
                missing_factors=[],
                source_citations=[_citation("peer-ntap", "peer_result")],
            )
        ]
    )
    target = TargetMarketData(
        ticker="NTNX",
        avg_daily_volume=2_000_000,
        pre_earnings_runup_pct=4.0,
        source_citations=[_citation("target-market", "market_data")],
    )

    first = build_strategy_decision(candidate=_candidate(), peer_signal=weak_signal, target=target)
    second = build_strategy_decision(candidate=_candidate(), peer_signal=weak_signal, target=target)

    assert first.status == StrategyStatus.REJECTED_WITH_REASON
    assert first.rejection_reasons == [RejectionReason.PEER_SIGNAL_TOO_WEAK]
    assert any(f.rule_name == "peer_signal_too_weak" for f in first.audit_trail.rule_facts)
    assert "target-market" in {c.citation_id for c in first.audit_trail.source_citations}
    assert first.audit_trail.model_dump(mode="json") == second.audit_trail.model_dump(mode="json")


def test_internal_rule_citation_is_json_safe() -> None:
    citation = internal_rule_citation("strategy-output-thresholds")

    dumped = citation.model_dump_json()
    assert "strategy-output-thresholds" in dumped
    assert "api_key" not in dumped
