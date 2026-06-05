from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from prescient.edge.models import (
    EventContext,
    SampleSizeVerdict,
    StrategyScorecard,
)
from prescient.edge.scorecard import build_scorecard
from prescient.edge.scorer import score_event
from prescient.edge.strategy import Strategy

_BASELINE_SOURCES = ("coin_flip", "always_up")
_SURVIVAL_MARGIN_PCT = 2.0  # must beat best baseline beat-implied rate by >= 2 points


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
    for strategy in strategies:
        scores = [
            score_event(prediction=strategy.predict(context), context=context)
            for context in contexts
        ]
        source = getattr(strategy, "source", strategy.__class__.__name__)
        raw[source] = build_scorecard(source=source, scores=scores)

    best_baseline_rate = max(
        (
            raw[name].beat_implied_rate or 0.0
            for name in _BASELINE_SOURCES
            if name in raw
        ),
        default=0.0,
    )

    finalized: dict[str, StrategyScorecard] = {}
    for source, card in raw.items():
        if source in _BASELINE_SOURCES:
            finalized[source] = card.model_copy(update={"survived": None})
            continue
        rate = card.beat_implied_rate
        survived = (
            rate is not None
            and card.sample_size_verdict != SampleSizeVerdict.TOO_FEW
            and rate >= best_baseline_rate + _SURVIVAL_MARGIN_PCT
        )
        notes = list(card.notes)
        if not survived:
            notes.append(
                "Did not clearly beat baselines on beat-implied - not tradeable."
            )
        finalized[source] = card.model_copy(
            update={"survived": survived, "notes": notes}
        )

    return EdgeBacktestResult(scorecards=finalized)
