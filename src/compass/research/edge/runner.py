from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from compass.research.edge.models import EventContext, SampleSizeVerdict, StrategyScorecard
from compass.research.edge.scorecard import build_scorecard
from compass.research.edge.scorer import score_event
from compass.research.edge.strategy import Strategy

_BASELINES = ("coin_flip", "always_up")
_SURVIVAL_MARGIN_PCT = 2.0


class EdgeBacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scorecards: dict[str, StrategyScorecard] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def run_edge_backtest(
    *,
    contexts: list[EventContext],
    strategies: list[Strategy],
) -> EdgeBacktestResult:
    raw: dict[str, StrategyScorecard] = {}
    pre_event_sources: set[str] = set()
    for strategy in strategies:
        source = getattr(strategy, "source", strategy.__class__.__name__)
        if source in raw:
            raise ValueError(f"Duplicate strategy source: {source!r}")
        scores = [
            score_event(prediction=strategy.predict(context), context=context)
            for context in contexts
        ]
        raw[source] = build_scorecard(source=source, scores=scores)
        if getattr(strategy, "exits_before_event", False):
            pre_event_sources.add(source)

    baselines_present = all(source in raw for source in _BASELINES)
    best_baseline_return = max(
        (raw[source].average_option_return_pct or 0.0 for source in _BASELINES if source in raw),
        default=0.0,
    )
    finalized: dict[str, StrategyScorecard] = {}
    for source, scorecard in raw.items():
        if source in _BASELINES:
            finalized[source] = scorecard.model_copy(update={"survived": None})
            continue
        average_return = scorecard.average_option_return_pct
        if source in pre_event_sources:
            survived = (
                scorecard.sample_size_verdict != SampleSizeVerdict.TOO_FEW
                and average_return is not None
                and average_return >= _SURVIVAL_MARGIN_PCT
            )
            notes = [
                *scorecard.notes,
                "Pre-event strategy uses the do-nothing baseline plus margin.",
            ]
        else:
            survived = (
                baselines_present
                and scorecard.sample_size_verdict != SampleSizeVerdict.TOO_FEW
                and average_return is not None
                and average_return > 0.0
                and average_return >= best_baseline_return + _SURVIVAL_MARGIN_PCT
            )
            notes = list(scorecard.notes)
            if not baselines_present:
                notes.append("Cannot determine survival: both baselines are required.")
        finalized[source] = scorecard.model_copy(
            update={"survived": survived, "notes": notes}
        )
    return EdgeBacktestResult(scorecards=finalized)
