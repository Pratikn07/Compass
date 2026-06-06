from __future__ import annotations

from statistics import median

from prescient.edge.models import EventScore, SampleSizeVerdict, StrategyScorecard

_HIGH_CONFIDENCE = 0.7


def _rate(flags: list[bool]) -> float | None:
    if not flags:
        return None
    return (sum(1 for flag in flags if flag) / len(flags)) * 100.0


def _sample_size_verdict(n: int) -> SampleSizeVerdict:
    if n < 30:
        return SampleSizeVerdict.TOO_FEW
    if n < 150:
        return SampleSizeVerdict.SUGGESTIVE
    if n < 500:
        return SampleSizeVerdict.MODERATE
    return SampleSizeVerdict.STRONG


def build_scorecard(*, source: str, scores: list[EventScore]) -> StrategyScorecard:
    evaluable = [s for s in scores if s.evaluable]

    directional = [
        s.direction_correct for s in evaluable if s.direction_correct is not None
    ]
    beat = [s.beat_implied for s in evaluable if s.beat_implied is not None]
    returns = [
        s.option_pnl.return_pct for s in evaluable if s.option_pnl is not None
    ]
    high_conf = [
        s.direction_correct
        for s in evaluable
        if s.confidence is not None
        and s.confidence >= _HIGH_CONFIDENCE
        and s.direction_correct is not None
    ]

    notes: list[str] = []
    verdict = _sample_size_verdict(len(evaluable))
    if verdict == SampleSizeVerdict.TOO_FEW:
        notes.append(
            f"{len(evaluable)} evaluable events - too few to trust; treat as a hint."
        )

    return StrategyScorecard(
        source=source,
        events_total=len(scores),
        events_evaluable=len(evaluable),
        directional_hit_rate=_rate(directional),
        beat_implied_rate=_rate(beat),
        average_option_return_pct=(
            sum(returns) / len(returns) if returns else None
        ),
        median_option_return_pct=(median(returns) if returns else None),
        high_confidence_hit_rate=_rate(high_conf),
        sample_size_verdict=verdict,
        survived=None,
        notes=notes,
    )
