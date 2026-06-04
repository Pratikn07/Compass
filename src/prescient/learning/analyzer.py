from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from statistics import median

from prescient.analytics import (
    PerformanceAnalyticsRequest,
    PerformanceMetrics,
    PerformanceObservation,
    calculate_performance_metrics,
)
from prescient.learning.models import (
    LearningAnalysis,
    LearningJournalRecord,
    LearningRecordType,
    OutcomeClassification,
)


def analyze_learning_records(records: list[LearningJournalRecord]) -> LearningAnalysis:
    decisions = [
        record for record in records if record.record_type == LearningRecordType.STRATEGY_DECISION
    ]
    outcomes = [
        record for record in records if record.record_type == LearningRecordType.TRADE_OUTCOME
    ]
    data_errors = [
        record for record in records if record.record_type == LearningRecordType.DATA_PROVIDER_ERROR
    ]

    warnings: list[str] = []
    excluded = Counter[str]()
    matched_outcomes: dict[int, LearningJournalRecord] = {}
    matched_classifications: dict[int, OutcomeClassification] = {}

    for outcome in outcomes:
        candidate_indexes = _find_matching_decisions(outcome, decisions)
        if len(candidate_indexes) == 1:
            decision_index = candidate_indexes[0]
            if decision_index in matched_outcomes:
                warnings.append("ambiguous_outcome_match: multiple outcomes matched one decision")
                excluded["ambiguous_outcome_match"] += 1
                continue

            classification = classify_outcome(outcome)
            matched_outcomes[decision_index] = outcome
            matched_classifications[decision_index] = classification
            continue

        if len(candidate_indexes) > 1:
            warnings.append("ambiguous_outcome_match: outcome matched multiple decisions")
            excluded["ambiguous_outcome_match"] += len(candidate_indexes)
        else:
            excluded["missing_decision_match"] += 1

    realized_pnls: list[float] = []
    win_pnls: list[float] = []
    loss_pnls: list[float] = []
    win_count = 0
    loss_count = 0
    flat_count = 0
    unknown_outcome_count = 0
    tunable_decisions: list[LearningJournalRecord] = []
    tunable_outcomes: list[LearningJournalRecord] = []
    tunable_classifications: list[OutcomeClassification] = []
    executed_count = 0

    for decision_index, decision in enumerate(decisions):
        strategy_status = str(decision.payload.get("strategy_status") or "")
        if strategy_status == "candidate_ready_for_analyst":
            executed_count += 1 if decision_index in matched_outcomes else 0
        else:
            _count_rejections(decision, excluded)

        outcome = matched_outcomes.get(decision_index)
        classification = matched_classifications.get(decision_index)
        if outcome is None or classification is None:
            unknown_outcome_count += 1
            excluded["missing_outcome"] += 1
            continue

        if classification == OutcomeClassification.OPEN:
            unknown_outcome_count += 1
            excluded["open_outcome"] += 1
            continue
        if classification == OutcomeClassification.UNKNOWN:
            unknown_outcome_count += 1
            excluded["unknown_outcome"] += 1
            continue
        if classification == OutcomeClassification.NOT_TRADEABLE:
            excluded["not_tradeable"] += 1
            continue

        pnl = _realized_pnl(outcome)
        if pnl is not None:
            realized_pnls.append(pnl)

        if classification == OutcomeClassification.WIN:
            win_count += 1
            if pnl is not None:
                win_pnls.append(pnl)
        elif classification == OutcomeClassification.LOSS:
            loss_count += 1
            if pnl is not None:
                loss_pnls.append(pnl)
        elif classification == OutcomeClassification.FLAT:
            flat_count += 1

        if _is_strategy_tunable(decision):
            tunable_decisions.append(decision)
            tunable_outcomes.append(outcome)
            tunable_classifications.append(classification)
        else:
            excluded["not_strategy_tunable"] += 1

    data_provider_error_counts = Counter[str]()
    for error_record in data_errors:
        provider = str(error_record.payload.get("provider") or error_record.target or "unknown")
        data_provider_error_counts[provider] += 1

    operational_recommendations: list[str] = []
    if data_provider_error_counts:
        operational_recommendations.append(
            "Data provider errors were present; do not loosen signal thresholds from bad data."
        )

    performance_metrics = _performance_metrics_from_realized_pnls(realized_pnls)
    closed_outcome_count = performance_metrics.closed_evaluable_outcome_count
    win_count = performance_metrics.win_count
    loss_count = performance_metrics.loss_count
    flat_count = performance_metrics.flat_count
    average_loss = _average(loss_pnls)
    average_win = _average(win_pnls)

    return LearningAnalysis(
        evaluated_decision_count=len(decisions),
        candidate_ready_count=sum(
            str(decision.payload.get("strategy_status") or "")
            == "candidate_ready_for_analyst"
            for decision in decisions
        ),
        executed_count=executed_count,
        closed_outcome_count=closed_outcome_count,
        win_count=win_count,
        loss_count=loss_count,
        flat_count=flat_count,
        unknown_outcome_count=unknown_outcome_count,
        average_realized_pnl=_average(realized_pnls),
        median_realized_pnl=median(realized_pnls) if realized_pnls else None,
        win_rate=performance_metrics.win_rate,
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=(
            average_win / abs(average_loss)
            if average_win is not None and average_loss not in {None, 0}
            else None
        ),
        largest_loss=min(loss_pnls) if loss_pnls else None,
        decision_to_execution_dropoff_count=max(
            0,
            sum(
                str(decision.payload.get("strategy_status") or "")
                == "candidate_ready_for_analyst"
                for decision in decisions
            )
            - executed_count,
        ),
        rejection_counts={
            key.replace("rejection:", ""): count
            for key, count in excluded.items()
            if key.startswith("rejection:")
        },
        data_provider_error_counts=dict(data_provider_error_counts),
        excluded_from_tuning={
            key: count for key, count in excluded.items() if not key.startswith("rejection:")
        },
        tunable_decisions=tunable_decisions,
        tunable_outcomes=tunable_outcomes,
        tunable_outcome_classifications=tunable_classifications,
        warnings=warnings,
        operational_recommendations=operational_recommendations,
    )


def classify_outcome(record: LearningJournalRecord) -> OutcomeClassification:
    status = str(record.payload.get("outcome_status") or "").lower()
    if status == "open":
        return OutcomeClassification.OPEN
    if status == "not_tradeable":
        return OutcomeClassification.NOT_TRADEABLE

    pnl = _realized_pnl(record)
    if pnl is None:
        return OutcomeClassification.UNKNOWN
    if pnl > 0:
        return OutcomeClassification.WIN
    if pnl < 0:
        return OutcomeClassification.LOSS
    return OutcomeClassification.FLAT


def _find_matching_decisions(
    outcome: LearningJournalRecord,
    decisions: list[LearningJournalRecord],
) -> list[int]:
    if outcome.decision_id is not None:
        direct = [
            index
            for index, decision in enumerate(decisions)
            if decision.decision_id == outcome.decision_id
        ]
        if direct:
            return direct

    if outcome.order_id is not None:
        direct = [
            index
            for index, decision in enumerate(decisions)
            if decision.order_id == outcome.order_id
            or decision.payload.get("order_id") == outcome.order_id
        ]
        if direct:
            return direct

    if (
        outcome.run_id is not None
        and outcome.target is not None
        and outcome.strategy_type is not None
        and outcome.trading_date is not None
    ):
        direct = [
            index
            for index, decision in enumerate(decisions)
            if decision.run_id == outcome.run_id
            and decision.target == outcome.target
            and decision.strategy_type == outcome.strategy_type
            and decision.trading_date == outcome.trading_date
        ]
        if direct:
            return direct

    if outcome.target is not None and outcome.theme is not None:
        return [
            index
            for index, decision in enumerate(decisions)
            if decision.target == outcome.target and decision.theme == outcome.theme
        ]

    return []


def _is_strategy_tunable(decision: LearningJournalRecord) -> bool:
    if str(decision.payload.get("strategy_status") or "") != "candidate_ready_for_analyst":
        return False
    if decision.payload.get("blocked_by") in {
        "risk",
        "liquidity",
        "market_hours",
        "broker",
        "data_provider",
    }:
        return False
    return True


def _realized_pnl(record: LearningJournalRecord) -> float | None:
    value = record.payload.get("realized_pnl")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _performance_metrics_from_realized_pnls(realized_pnls: list[float]) -> PerformanceMetrics:
    base_date = date(1970, 1, 1)
    observations = [
        PerformanceObservation(
            observation_id=f"learning-outcome-{index}",
            ticker="LEARNING",
            entry_date=base_date + timedelta(days=index),
            exit_date=base_date + timedelta(days=index),
            allocated_capital=0.0,
            strategy_net_pnl=pnl,
            benchmark_entry_price=None,
            benchmark_exit_price=None,
        )
        for index, pnl in enumerate(realized_pnls)
    ]
    return calculate_performance_metrics(
        PerformanceAnalyticsRequest(observations=observations)
    )


def _count_rejections(decision: LearningJournalRecord, excluded: Counter[str]) -> None:
    raw_reasons = decision.payload.get("rejection_reasons")
    if isinstance(raw_reasons, list):
        for reason in raw_reasons:
            excluded[f"rejection:{reason}"] += 1
