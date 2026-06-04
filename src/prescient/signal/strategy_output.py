from __future__ import annotations

from prescient.data import TranscriptSummary
from prescient.journal import (
    DecisionLayer,
    DecisionType,
    SourceCitation,
    audit_trail,
    internal_rule_citation,
    merge_source_citations,
    rule_fact,
)
from prescient.signal.models import (
    CandidateBrief,
    CandidateDetectionStatus,
    DecisionAudit,
    EarningsCandidateDecision,
    OptionContractSnapshot,
    PeerScore,
    PeerSignal,
    RejectionReason,
    RejectionStage,
    StrategyDecision,
    StrategySettings,
    StrategyStatus,
    TargetFilterDecision,
    TargetFilterStatus,
    TargetMarketData,
    TechnicalIndicatorSnapshot,
)
from prescient.signal.rejections import build_rejection_details
from prescient.signal.strategy_types import PreferredExpression
from prescient.signal.target_filters import run_target_filters


_DEFAULT_SETTINGS = StrategySettings()


def build_strategy_decision(
    candidate: EarningsCandidateDecision,
    peer_signal: PeerSignal,
    target: TargetMarketData | None,
    indicator_snapshot: TechnicalIndicatorSnapshot | None = None,
    options_chain: list[OptionContractSnapshot] | None = None,
    preferred_expression: PreferredExpression = "CALL_OPTION",
    settings: StrategySettings = _DEFAULT_SETTINGS,
    peer_summaries: list[TranscriptSummary] | None = None,
) -> StrategyDecision:
    option_contracts = options_chain or []
    audit = _decision_audit(
        candidate=candidate,
        peer_signal=peer_signal,
        target=target,
        indicator_snapshot=indicator_snapshot,
        options_chain=option_contracts,
        settings=settings,
    )
    source_citations = _source_citations(
        candidate=candidate,
        peer_signal=peer_signal,
        target=target,
        indicator_snapshot=indicator_snapshot,
        options_chain=option_contracts,
    )
    base_rule_facts = _base_rule_facts(peer_signal=peer_signal, settings=settings)

    if _candidate_prerequisites_failed(candidate):
        filter_decision = run_target_filters(
            candidate=candidate,
            peer_signal=peer_signal,
            target_data=target,
            preferred_expression=preferred_expression,
            options_chain=option_contracts,
            settings=settings,
        )
        return _rejected(
            rejection_reasons=filter_decision.rejection_reasons,
            stage=RejectionStage.CANDIDATE_DETECTION,
            audit=audit,
            source_citations=source_citations,
            rule_facts=base_rule_facts,
        )

    if _all_peer_data_missing(peer_signal):
        return _rejected(
            rejection_reasons=[RejectionReason.MISSING_DATA],
            stage=RejectionStage.PEER_SIGNAL,
            audit=audit,
            source_citations=source_citations,
            rule_facts=[
                *base_rule_facts,
                rule_fact(
                    "all_peer_data_missing",
                    passed=False,
                    observed_value=True,
                    reason=RejectionReason.MISSING_DATA.value,
                ),
            ],
        )

    if not peer_signal.passes_thresholds:
        return _rejected(
            rejection_reasons=[RejectionReason.PEER_SIGNAL_TOO_WEAK],
            stage=RejectionStage.PEER_SIGNAL,
            audit=audit,
            source_citations=source_citations,
            rule_facts=[
                *base_rule_facts,
                rule_fact(
                    "peer_signal_too_weak",
                    passed=False,
                    threshold=settings.min_average_peer_score,
                    observed_value=peer_signal.average_peer_score,
                    reason=RejectionReason.PEER_SIGNAL_TOO_WEAK.value,
                ),
            ],
        )

    filter_decision = run_target_filters(
        candidate=candidate,
        peer_signal=peer_signal,
        target_data=target,
        preferred_expression=preferred_expression,
        options_chain=option_contracts,
        settings=settings,
    )
    if filter_decision.status == TargetFilterStatus.REJECTED:
        return _rejected(
            rejection_reasons=filter_decision.rejection_reasons,
            stage=RejectionStage.TARGET_FILTER,
            audit=audit,
            source_citations=source_citations,
            rule_facts=[
                *base_rule_facts,
                *[
                    rule_fact(
                        reason.value,
                        passed=False,
                        reason=reason.value,
                    )
                    for reason in filter_decision.rejection_reasons
                ],
            ],
        )

    candidate_brief = _build_candidate_brief(
        candidate=candidate,
        peer_signal=peer_signal,
        filter_decision=filter_decision,
        indicator_snapshot=indicator_snapshot,
        peer_summaries=peer_summaries,
        source_citations=source_citations,
    )
    return StrategyDecision(
        status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        candidate=candidate_brief,
        rejection_reasons=[],
        rejection_details=[],
        audit=audit,
        claude_analysis_allowed=True,
        audit_trail=_strategy_audit_trail(
            status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
            audit=audit,
            source_citations=source_citations,
            rule_facts=base_rule_facts,
        ),
    )


def _candidate_prerequisites_failed(candidate: EarningsCandidateDecision) -> bool:
    return (
        candidate.status == CandidateDetectionStatus.REJECTED
        or candidate.theme is None
        or candidate.earnings_date is None
        or bool(candidate.rejection_reasons)
    )


def _all_peer_data_missing(peer_signal: PeerSignal) -> bool:
    if not peer_signal.peer_scores:
        return False

    return all(
        score.score == 0
        and not score.positive_factors
        and not score.negative_factors
        and bool(score.missing_factors)
        for score in peer_signal.peer_scores
    )


def _decision_audit(
    *,
    candidate: EarningsCandidateDecision,
    peer_signal: PeerSignal,
    target: TargetMarketData | None,
    indicator_snapshot: TechnicalIndicatorSnapshot | None,
    options_chain: list[OptionContractSnapshot],
    settings: StrategySettings,
) -> DecisionAudit:
    return DecisionAudit(
        target=candidate.target,
        theme=candidate.theme,
        peer_scores=peer_signal.peer_scores,
        thresholds={
            "min_positive_peer_ratio": settings.min_positive_peer_ratio,
            "min_average_peer_score": settings.min_average_peer_score,
            "min_avg_daily_volume": settings.min_avg_daily_volume,
            "max_target_runup_pct": settings.max_target_runup_pct,
            "allow_stock_fallback": settings.allow_stock_fallback,
        },
        missing_peer_factor_count=peer_signal.missing_data_count,
        all_peer_data_missing=_all_peer_data_missing(peer_signal),
        target_market_data_present=target is not None,
        option_contract_count=len(options_chain),
        indicator_snapshot_present=indicator_snapshot is not None,
        indicator_missing_fields=indicator_snapshot.missing_fields
        if indicator_snapshot is not None
        else [],
        indicator_source=indicator_snapshot.source if indicator_snapshot is not None else None,
        indicator_freshness=indicator_snapshot.freshness
        if indicator_snapshot is not None
        else None,
        source_citations=_source_citations(
            candidate=candidate,
            peer_signal=peer_signal,
            target=target,
            indicator_snapshot=indicator_snapshot,
            options_chain=options_chain,
        ),
    )


def _build_candidate_brief(
    candidate: EarningsCandidateDecision,
    peer_signal: PeerSignal,
    filter_decision: TargetFilterDecision,
    indicator_snapshot: TechnicalIndicatorSnapshot | None,
    peer_summaries: list[TranscriptSummary] | None = None,
    source_citations: list[SourceCitation] | None = None,
) -> CandidateBrief:
    if candidate.theme is None or candidate.earnings_date is None:
        raise ValueError("Candidate brief requires a configured theme and earnings date.")

    return CandidateBrief(
        target=candidate.target,
        theme=candidate.theme,
        earnings_date=candidate.earnings_date,
        report_time=candidate.report_time,
        direction="bullish",
        peer_signal_score=peer_signal.average_peer_score,
        positive_peer_ratio=peer_signal.positive_peer_ratio,
        reported_peers=candidate.reported_peers,
        peer_scores=peer_signal.peer_scores,
        main_thesis=_main_thesis(candidate, peer_signal),
        supporting_evidence=_supporting_evidence(peer_signal),
        contradictions=_contradictions(peer_signal, filter_decision),
        recommended_expression=filter_decision.recommended_expression,
        technical_indicators=indicator_snapshot,
        strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        peer_summaries=peer_summaries or [],
        source_citations=source_citations or [],
    )


def _main_thesis(candidate: EarningsCandidateDecision, peer_signal: PeerSignal) -> str:
    if candidate.theme is None or candidate.earnings_date is None:
        raise ValueError("Candidate thesis requires a configured theme and earnings date.")

    total_peer_count = _total_peer_count(peer_signal)
    return (
        f"Bullish {candidate.theme} read-through for {candidate.target}: "
        f"{peer_signal.positive_peer_count} of {total_peer_count} peers have positive "
        f"earnings signal ahead of {candidate.earnings_date.isoformat()} earnings."
    )


def _supporting_evidence(peer_signal: PeerSignal) -> list[str]:
    total_peer_count = _total_peer_count(peer_signal)
    evidence = [
        (
            f"{peer_signal.positive_peer_count} of {total_peer_count} peers had "
            "positive scores."
        )
    ]

    revenue_beat_count = _factor_count(peer_signal.peer_scores, "revenue_beat")
    if revenue_beat_count:
        evidence.append(
            f"{revenue_beat_count} {_peer_word(revenue_beat_count)} beat revenue estimates."
        )

    positive_guidance_count = _factor_count(peer_signal.peer_scores, "positive_guidance")
    if positive_guidance_count:
        evidence.append(
            f"{positive_guidance_count} {_peer_word(positive_guidance_count)} showed "
            "positive guidance."
        )

    positive_theme_driver_count = _factor_count(
        peer_signal.peer_scores,
        "positive_theme_driver",
    )
    if positive_theme_driver_count:
        evidence.append(
            f"{positive_theme_driver_count} {_peer_word(positive_theme_driver_count)} "
            "confirmed theme-driver evidence."
        )

    return evidence


def _contradictions(
    peer_signal: PeerSignal,
    filter_decision: TargetFilterDecision,
) -> list[str]:
    contradictions: list[str] = []

    if peer_signal.negative_peer_count:
        contradictions.append(
            f"{peer_signal.negative_peer_count} {_peer_word(peer_signal.negative_peer_count)} "
            "had negative scores."
        )

    if RejectionReason.OPTIONS_TOO_ILLIQUID in filter_decision.warnings:
        contradictions.append("Options liquidity failed; using stock fallback.")

    return contradictions


def _factor_count(peer_scores: list[PeerScore], factor: str) -> int:
    return sum(factor in score.positive_factors for score in peer_scores)


def _total_peer_count(peer_signal: PeerSignal) -> int:
    return len(peer_signal.peer_scores) or peer_signal.positive_peer_count


def _peer_word(count: int) -> str:
    return "peer" if count == 1 else "peers"


def _rejected(
    *,
    rejection_reasons: list[RejectionReason],
    stage: RejectionStage,
    audit: DecisionAudit,
    source_citations: list[SourceCitation],
    rule_facts,
) -> StrategyDecision:
    deduplicated_reasons = _deduplicate_reasons(rejection_reasons)
    return StrategyDecision(
        status=StrategyStatus.REJECTED_WITH_REASON,
        candidate=None,
        rejection_reasons=deduplicated_reasons,
        rejection_details=build_rejection_details(deduplicated_reasons, stage),
        audit=audit,
        claude_analysis_allowed=False,
        audit_trail=_strategy_audit_trail(
            status=StrategyStatus.REJECTED_WITH_REASON,
            audit=audit,
            source_citations=source_citations,
            rule_facts=rule_facts,
            seed=":".join(reason.value for reason in deduplicated_reasons),
        ),
    )


def _deduplicate_reasons(rejection_reasons: list[RejectionReason]) -> list[RejectionReason]:
    seen: set[RejectionReason] = set()
    deduplicated: list[RejectionReason] = []

    for reason in rejection_reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduplicated.append(reason)

    return deduplicated


def _source_citations(
    *,
    candidate: EarningsCandidateDecision,
    peer_signal: PeerSignal,
    target: TargetMarketData | None,
    indicator_snapshot: TechnicalIndicatorSnapshot | None,
    options_chain: list[OptionContractSnapshot],
) -> list[SourceCitation]:
    return merge_source_citations(
        candidate.upcoming_event.source_citations
        if candidate.upcoming_event is not None
        else [],
        [citation for score in peer_signal.peer_scores for citation in score.source_citations],
        target.source_citations if target is not None else [],
        indicator_snapshot.source_citations if indicator_snapshot is not None else [],
        [citation for option in options_chain for citation in option.source_citations],
        [internal_rule_citation("strategy-output-thresholds")],
    )


def _base_rule_facts(
    *,
    peer_signal: PeerSignal,
    settings: StrategySettings,
):
    return [
        rule_fact(
            "min_positive_peer_ratio",
            passed=peer_signal.positive_peer_ratio >= settings.min_positive_peer_ratio,
            threshold=settings.min_positive_peer_ratio,
            observed_value=peer_signal.positive_peer_ratio,
        ),
        rule_fact(
            "min_average_peer_score",
            passed=peer_signal.average_peer_score >= settings.min_average_peer_score,
            threshold=settings.min_average_peer_score,
            observed_value=peer_signal.average_peer_score,
        ),
    ]


def _strategy_audit_trail(
    *,
    status: StrategyStatus,
    audit: DecisionAudit,
    source_citations: list[SourceCitation],
    rule_facts,
    seed: str | None = None,
):
    return audit_trail(
        decision_type=DecisionType.STRATEGY_DECISION,
        decision_layer=DecisionLayer.SIGNAL,
        target=audit.target,
        theme=audit.theme,
        source_citations=source_citations,
        rule_facts=rule_facts,
        seed=seed or f"{status.value}:{audit.target}:{audit.theme}",
    )
