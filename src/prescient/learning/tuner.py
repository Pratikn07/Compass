from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prescient.learning.models import (
    DEFAULT_LEARNABLE_PARAMETER_PATHS,
    FORBIDDEN_AUTO_TUNED_PARAMETER_PATHS,
    LearnableParameterPolicy,
    LearningAnalysis,
    LearningMode,
    OutcomeClassification,
    ParameterProposal,
    ParameterProposalReason,
    ParameterProposalStatus,
)


def generate_parameter_proposals(
    *,
    analysis: LearningAnalysis,
    settings_snapshot: Mapping[str, Any],
    policies: Sequence[LearnableParameterPolicy],
    mode: LearningMode,
    execution_mode: str,
    fail_closed: bool = False,
) -> list[ParameterProposal]:
    proposals = [
        _proposal_for_policy(
            analysis=analysis,
            settings_snapshot=settings_snapshot,
            policy=policy,
            fail_closed=fail_closed,
        )
        for policy in policies
    ]

    if mode == LearningMode.AUTO_APPLY_SAFE and execution_mode == "live":
        return [
            _reject_for_live_mode(proposal)
            if proposal.status == ParameterProposalStatus.PROPOSED
            else proposal
            for proposal in proposals
        ]

    if mode != LearningMode.AUTO_APPLY_SAFE:
        return proposals

    return [
        proposal.model_copy(
            update={
                "status": ParameterProposalStatus.APPLIED,
                "applied": True,
            }
        )
        if _can_apply(proposal)
        else proposal
        for proposal in proposals
    ]


def _proposal_for_policy(
    *,
    analysis: LearningAnalysis,
    settings_snapshot: Mapping[str, Any],
    policy: LearnableParameterPolicy,
    fail_closed: bool,
) -> ParameterProposal:
    current_value = _get_setting(settings_snapshot, policy.path)
    sample_size = len(analysis.tunable_outcomes)
    distinct_days = len(
        {
            decision.trading_date
            for decision in analysis.tunable_decisions
            if decision.trading_date is not None
        }
    )

    base = {
        "path": policy.path,
        "current_value": current_value if current_value is not None else "",
        "sample_size": sample_size,
        "distinct_trading_days": distinct_days,
        "confidence": _confidence(sample_size, policy.min_closed_outcomes),
        "auto_apply_allowed": policy.auto_apply_allowed,
        "applied": False,
        "min_value": policy.min_value,
        "max_value": policy.max_value,
        "max_daily_delta": policy.max_daily_delta,
    }

    if policy.path in FORBIDDEN_AUTO_TUNED_PARAMETER_PATHS:
        return ParameterProposal(
            **base,
            proposed_value=current_value if current_value is not None else "",
            status=ParameterProposalStatus.REJECTED,
            reasons=[ParameterProposalReason.SAFETY_PARAMETER_FORBIDDEN],
            evidence_summary=f"{policy.path} is a safety parameter and cannot be tuned.",
        )

    if policy.path not in DEFAULT_LEARNABLE_PARAMETER_PATHS:
        return ParameterProposal(
            **base,
            proposed_value=current_value if current_value is not None else "",
            status=ParameterProposalStatus.REJECTED,
            reasons=[ParameterProposalReason.OUTSIDE_ALLOWLIST],
            evidence_summary=f"{policy.path} is not in the R6.2 learnable parameter allowlist.",
        )

    if current_value is None:
        return ParameterProposal(
            **base,
            proposed_value="",
            status=ParameterProposalStatus.REJECTED,
            reasons=[ParameterProposalReason.CURRENT_VALUE_MISSING],
            evidence_summary=f"Current value for {policy.path} was not available.",
        )

    if fail_closed:
        return ParameterProposal(
            **base,
            proposed_value=current_value,
            status=ParameterProposalStatus.NO_OP,
            reasons=[ParameterProposalReason.DATA_QUALITY_ISSUE],
            evidence_summary="Learning run failed closed because input data was not reliable.",
        )

    if sample_size < policy.min_closed_outcomes or distinct_days < policy.min_distinct_trading_days:
        return ParameterProposal(
            **base,
            proposed_value=current_value,
            status=ParameterProposalStatus.NO_OP,
            reasons=[ParameterProposalReason.INSUFFICIENT_SAMPLE],
            evidence_summary=(
                f"{policy.path} needs at least {policy.min_closed_outcomes} closed "
                f"outcomes across {policy.min_distinct_trading_days} distinct trading days."
            ),
        )

    proposed_value = _proposed_value_for_policy(policy, current_value, analysis)
    if proposed_value == current_value:
        return ParameterProposal(
            **base,
            proposed_value=current_value,
            status=ParameterProposalStatus.NO_OP,
            reasons=[ParameterProposalReason.EVIDENCE_SUPPORTED],
            evidence_summary=f"No parameter movement was supported for {policy.path}.",
        )

    if not _inside_bounds(proposed_value, policy):
        return ParameterProposal(
            **base,
            proposed_value=proposed_value,
            status=ParameterProposalStatus.REJECTED,
            reasons=[ParameterProposalReason.OUTSIDE_BOUNDS],
            evidence_summary=f"Proposed value for {policy.path} was outside policy bounds.",
        )

    if not policy.auto_apply_allowed:
        return ParameterProposal(
            **base,
            proposed_value=proposed_value,
            status=ParameterProposalStatus.REVIEW_ONLY,
            reasons=[ParameterProposalReason.EVIDENCE_SUPPORTED],
            evidence_summary=_evidence_summary(policy.path, proposed_value, analysis),
        )

    return ParameterProposal(
        **base,
        proposed_value=proposed_value,
        status=ParameterProposalStatus.PROPOSED,
        reasons=[ParameterProposalReason.EVIDENCE_SUPPORTED],
        evidence_summary=_evidence_summary(policy.path, proposed_value, analysis),
    )


def _proposed_value_for_policy(
    policy: LearnableParameterPolicy,
    current_value: Any,
    analysis: LearningAnalysis,
) -> float | int | bool | str:
    if not isinstance(current_value, int | float) or isinstance(current_value, bool):
        return current_value

    if analysis.loss_count <= 0:
        return current_value

    if policy.path == "strategy.min_positive_peer_ratio":
        if _average_feature(analysis, "peer_signal", "positive_peer_ratio") < float(current_value):
            return _rounded(current_value + (policy.max_daily_delta or 0))
        return current_value

    if policy.path == "strategy.min_average_peer_score":
        if _average_feature(analysis, "peer_signal", "average_peer_score") < float(current_value):
            return _rounded(current_value + (policy.max_daily_delta or 0))
        return current_value

    if policy.path == "strategy.max_target_runup_pct":
        if _average_feature(analysis, "target_filters", "target_runup_pct") >= float(current_value):
            return _rounded(current_value - (policy.max_daily_delta or 0))
        return current_value

    return current_value


def _average_feature(
    analysis: LearningAnalysis,
    payload_key: str,
    feature_key: str,
) -> float:
    values: list[float] = []
    for decision, classification in zip(
        analysis.tunable_decisions,
        analysis.tunable_outcome_classifications,
        strict=True,
    ):
        if classification != OutcomeClassification.LOSS:
            continue
        raw_container = decision.payload.get(payload_key)
        if not isinstance(raw_container, dict):
            continue
        value = raw_container.get(feature_key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            values.append(float(value))

    if not values:
        return 0.0
    return sum(values) / len(values)


def _evidence_summary(
    path: str,
    proposed_value: float | int | bool | str,
    analysis: LearningAnalysis,
) -> str:
    return (
        f"{analysis.loss_count} losses and {analysis.win_count} wins in "
        f"{analysis.closed_outcome_count} closed tunable outcomes support setting "
        f"{path} to {proposed_value}."
    )


def _reject_for_live_mode(proposal: ParameterProposal) -> ParameterProposal:
    reasons = list(dict.fromkeys([*proposal.reasons, ParameterProposalReason.LIVE_MODE_BLOCKED]))
    return proposal.model_copy(
        update={
            "status": ParameterProposalStatus.REJECTED,
            "reasons": reasons,
            "applied": False,
        }
    )


def _can_apply(proposal: ParameterProposal) -> bool:
    return (
        proposal.status == ParameterProposalStatus.PROPOSED
        and proposal.auto_apply_allowed
        and not proposal.applied
    )


def _inside_bounds(
    proposed_value: float | int | bool | str,
    policy: LearnableParameterPolicy,
) -> bool:
    if isinstance(proposed_value, bool) or isinstance(policy.min_value, bool):
        return proposed_value in {policy.min_value, policy.max_value}
    if not isinstance(proposed_value, int | float):
        return False
    return float(policy.min_value) <= float(proposed_value) <= float(policy.max_value)


def _get_setting(settings_snapshot: Mapping[str, Any], path: str) -> Any:
    current: Any = settings_snapshot
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _confidence(sample_size: int, minimum: int) -> float:
    if minimum <= 0:
        return 1.0
    return min(1.0, sample_size / minimum)


def _rounded(value: float | int) -> float | int:
    if isinstance(value, int):
        return value
    return round(float(value), 4)
