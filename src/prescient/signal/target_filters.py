from __future__ import annotations

from datetime import timedelta

from prescient.signal.models import (
    CandidateDetectionStatus,
    CandidateRejectionReason,
    EarningsCandidateDecision,
    OptionContractSnapshot,
    PeerSignal,
    RejectionReason,
    StrategySettings,
    TargetFilterDecision,
    TargetFilterStatus,
    TargetMarketData,
)
from prescient.signal.strategy_types import PreferredExpression


_DEFAULT_SETTINGS = StrategySettings()
_SUPPORTED_EXPRESSIONS = {"CALL_OPTION", "STOCK"}


def run_target_filters(
    candidate: EarningsCandidateDecision,
    peer_signal: PeerSignal,
    target_data: TargetMarketData | None,
    preferred_expression: PreferredExpression = "CALL_OPTION",
    options_chain: list[OptionContractSnapshot] | None = None,
    settings: StrategySettings = _DEFAULT_SETTINGS,
) -> TargetFilterDecision:
    if preferred_expression not in _SUPPORTED_EXPRESSIONS:
        raise ValueError(f"Unsupported target filter expression: {preferred_expression}")

    prerequisite_rejections = _candidate_rejection_reasons(candidate)
    if prerequisite_rejections:
        return _rejected_decision(
            candidate=candidate,
            rejection_reasons=prerequisite_rejections,
        )

    if not peer_signal.passes_thresholds:
        return _rejected_decision(
            candidate=candidate,
            rejection_reasons=[RejectionReason.PEER_SIGNAL_TOO_WEAK],
        )

    market_rejections = _target_market_rejection_reasons(target_data, settings)
    if market_rejections:
        return _rejected_decision(
            candidate=candidate,
            rejection_reasons=market_rejections,
        )

    if preferred_expression == "STOCK":
        return _passed_decision(
            candidate=candidate,
            recommended_expression="STOCK",
            selected_option=None,
            warnings=[],
        )

    selected_option = _select_liquid_call_option(
        candidate=candidate,
        options_chain=options_chain or [],
        settings=settings,
    )
    if selected_option is not None:
        return _passed_decision(
            candidate=candidate,
            recommended_expression="CALL_OPTION",
            selected_option=selected_option,
            warnings=[],
        )

    if settings.allow_stock_fallback:
        return _passed_decision(
            candidate=candidate,
            recommended_expression="STOCK",
            selected_option=None,
            warnings=[RejectionReason.OPTIONS_TOO_ILLIQUID],
        )

    return _rejected_decision(
        candidate=candidate,
        rejection_reasons=[RejectionReason.OPTIONS_TOO_ILLIQUID],
    )


def _candidate_rejection_reasons(
    candidate: EarningsCandidateDecision,
) -> list[RejectionReason]:
    reasons: list[RejectionReason] = []

    if (
        candidate.theme is None
        or CandidateRejectionReason.THEME_NOT_CONFIGURED in candidate.rejection_reasons
    ):
        reasons.append(RejectionReason.THEME_NOT_CONFIGURED)

    if (
        candidate.earnings_date is None
        or CandidateRejectionReason.EARNINGS_DATE_MISSING in candidate.rejection_reasons
        or CandidateRejectionReason.OUTSIDE_EARNINGS_WINDOW in candidate.rejection_reasons
    ):
        reasons.append(RejectionReason.EARNINGS_DATE_UNCERTAIN)

    if (
        candidate.status == CandidateDetectionStatus.REJECTED
        and CandidateRejectionReason.INSUFFICIENT_REPORTED_PEERS
        in candidate.rejection_reasons
    ):
        reasons.append(RejectionReason.INSUFFICIENT_PEERS_REPORTED)

    return reasons


def _target_market_rejection_reasons(
    target_data: TargetMarketData | None,
    settings: StrategySettings,
) -> list[RejectionReason]:
    if (
        target_data is None
        or target_data.avg_daily_volume is None
        or target_data.pre_earnings_runup_pct is None
    ):
        return [RejectionReason.MISSING_DATA]

    reasons: list[RejectionReason] = []
    if (
        target_data.avg_daily_volume < settings.min_avg_daily_volume
        or target_data.is_extremely_illiquid
    ):
        reasons.append(RejectionReason.TARGET_TOO_ILLIQUID)
    if target_data.pre_earnings_runup_pct > settings.max_target_runup_pct:
        reasons.append(RejectionReason.TARGET_ALREADY_OVEREXTENDED)
    if target_data.has_conflicting_news:
        reasons.append(RejectionReason.CONFLICTING_NEWS)
    if target_data.has_invalidating_event:
        reasons.append(RejectionReason.TARGET_EVENT_INVALIDATES_PEER_COMPARISON)

    return reasons


def _select_liquid_call_option(
    candidate: EarningsCandidateDecision,
    options_chain: list[OptionContractSnapshot],
    settings: StrategySettings,
) -> OptionContractSnapshot | None:
    if candidate.earnings_date is None:
        return None

    max_expiration_date = candidate.earnings_date + timedelta(
        days=settings.max_option_expiration_days_after_earnings
    )

    for option in options_chain:
        if (
            option.ticker != candidate.target
            or option.option_type != "CALL"
            or option.expiration_date < candidate.earnings_date
            or option.expiration_date > max_expiration_date
        ):
            continue
        if _has_liquid_option_quote(option, settings):
            return option

    return None


def _has_liquid_option_quote(
    option: OptionContractSnapshot,
    settings: StrategySettings,
) -> bool:
    if (
        option.bid is None
        or option.ask is None
        or option.open_interest is None
        or option.bid <= 0
        or option.ask <= 0
        or option.ask < option.bid
        or option.open_interest < settings.min_option_open_interest
    ):
        return False

    midpoint = (option.bid + option.ask) / 2
    spread_pct = ((option.ask - option.bid) / midpoint) * 100
    return spread_pct <= settings.max_options_bid_ask_spread_pct


def _passed_decision(
    candidate: EarningsCandidateDecision,
    recommended_expression: PreferredExpression,
    selected_option: OptionContractSnapshot | None,
    warnings: list[RejectionReason],
) -> TargetFilterDecision:
    return TargetFilterDecision(
        target=candidate.target,
        theme=candidate.theme,
        status=TargetFilterStatus.PASSED,
        recommended_expression=recommended_expression,
        selected_option=selected_option,
        rejection_reasons=[],
        warnings=warnings,
    )


def _rejected_decision(
    candidate: EarningsCandidateDecision,
    rejection_reasons: list[RejectionReason],
) -> TargetFilterDecision:
    return TargetFilterDecision(
        target=candidate.target,
        theme=candidate.theme,
        status=TargetFilterStatus.REJECTED,
        recommended_expression="NONE",
        selected_option=None,
        rejection_reasons=rejection_reasons,
        warnings=[],
    )
