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
_SURVIVAL_MARGIN_PCT = 2.0  # must beat best baseline AVERAGE return by >= 2 points


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
        if source in raw:
            raise ValueError(f"Duplicate strategy source: {source!r}")
        raw[source] = build_scorecard(source=source, scores=scores)

    both_baselines_present = all(name in raw for name in _BASELINE_SOURCES)

    # NOTE (denominator caveat): survival compares average_option_return_pct across
    # strategies, but the buy strategies measure return on PREMIUM while short_vol
    # measures return on CAPITAL-AT-RISK (W). These denominators differ, so the
    # comparison is imperfect. The bias is conservative: premium-based buy returns
    # are larger-scaled, making the bar HARDER for short_vol, never easier. For a
    # disprove-first tool this is the safe direction (it never fabricates a
    # "survived"); but a short_vol "not survived" should be read with this caveat,
    # not as proof the vol premium is absent. Normalizing denominators would require
    # an invented leverage factor, so we document rather than fabricate one.
    best_baseline_return = max(
        (
            raw[name].average_option_return_pct or 0.0
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
        avg_return = card.average_option_return_pct
        survived = (
            both_baselines_present
            and card.sample_size_verdict != SampleSizeVerdict.TOO_FEW
            and avg_return is not None
            and avg_return > 0.0
            and avg_return >= best_baseline_return + _SURVIVAL_MARGIN_PCT
        )
        notes = list(card.notes)
        if not both_baselines_present:
            notes.append(
                "Cannot determine survival: both coin_flip and always_up "
                "baselines are required."
            )
        elif not survived:
            notes.append(
                "Did not clearly beat baselines on average return - not tradeable."
            )
        finalized[source] = card.model_copy(
            update={"survived": survived, "notes": notes}
        )

    return EdgeBacktestResult(scorecards=finalized)
