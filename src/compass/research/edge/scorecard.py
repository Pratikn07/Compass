from __future__ import annotations

from statistics import median

from compass.research.edge.models import EventScore, SampleSizeVerdict, StrategyScorecard

_HIGH_CONFIDENCE = 0.7


def _rate(flags: list[bool]) -> float | None:
    if not flags:
        return None
    return (sum(flags) / len(flags)) * 100.0


def _sample_size_verdict(count: int) -> SampleSizeVerdict:
    if count < 30:
        return SampleSizeVerdict.TOO_FEW
    if count < 150:
        return SampleSizeVerdict.SUGGESTIVE
    if count < 500:
        return SampleSizeVerdict.MODERATE
    return SampleSizeVerdict.STRONG


def build_scorecard(*, source: str, scores: list[EventScore]) -> StrategyScorecard:
    evaluable = [score for score in scores if score.evaluable]
    directional = [
        score.direction_correct
        for score in evaluable
        if score.direction_correct is not None
    ]
    beat_implied = [
        score.beat_implied for score in evaluable if score.beat_implied is not None
    ]
    returns = [
        score.option_pnl.return_pct for score in evaluable if score.option_pnl is not None
    ]
    high_confidence = [
        score.direction_correct
        for score in evaluable
        if score.confidence is not None
        and score.confidence >= _HIGH_CONFIDENCE
        and score.direction_correct is not None
    ]
    verdict = _sample_size_verdict(len(evaluable))
    notes = []
    if verdict == SampleSizeVerdict.TOO_FEW:
        notes.append(f"{len(evaluable)} evaluable events - too few to trust; treat as a hint.")
    return StrategyScorecard(
        source=source,
        events_total=len(scores),
        events_evaluable=len(evaluable),
        directional_hit_rate=_rate(directional),
        beat_implied_rate=_rate(beat_implied),
        average_option_return_pct=sum(returns) / len(returns) if returns else None,
        median_option_return_pct=median(returns) if returns else None,
        high_confidence_hit_rate=_rate(high_confidence),
        sample_size_verdict=verdict,
        notes=notes,
    )
