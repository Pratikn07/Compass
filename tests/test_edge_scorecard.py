from __future__ import annotations

from datetime import date

import pytest

from prescient.edge.models import EventScore, OptionPnl, SampleSizeVerdict


def _score(direction_correct, beat_implied, ret_pct, conf, evaluable=True):
    return EventScore(
        ticker="MU", as_of_date=date(2024, 6, 25), source="reaction_aware_peer",
        evaluable=evaluable,
        not_evaluable_reason=None if evaluable else "missing_implied_move",
        direction_correct=direction_correct, beat_implied=beat_implied,
        implied_move_pct=8.0, realized_move_pct=6.0,
        option_pnl=(
            OptionPnl(entry_premium=4.0, exit_value=6.0, cost_haircut=0.2,
                      net_pnl=1.8, return_pct=ret_pct)
            if evaluable else None
        ),
        confidence=conf,
    )


def test_scorecard_rates_only_evaluable_events() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [
        _score(True, True, 45.0, 0.8),
        _score(False, False, -30.0, 0.6),
        _score(None, None, 0.0, 0.0, evaluable=False),
    ]
    card = build_scorecard(source="reaction_aware_peer", scores=scores)
    assert card.events_total == 3
    assert card.events_evaluable == 2
    assert card.directional_hit_rate == pytest.approx(50.0)
    assert card.beat_implied_rate == pytest.approx(50.0)
    assert card.average_option_return_pct == pytest.approx(7.5)
    assert card.sample_size_verdict == SampleSizeVerdict.TOO_FEW


def test_high_confidence_hit_rate_uses_only_confident_events() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [
        _score(True, True, 10.0, 0.8),   # confident, correct
        _score(False, False, -10.0, 0.9),  # confident, wrong
        _score(True, True, 10.0, 0.3),   # not confident -> excluded
    ]
    card = build_scorecard(source="reaction_aware_peer", scores=scores)
    assert card.high_confidence_hit_rate == pytest.approx(50.0)


def test_sample_size_verdict_thresholds() -> None:
    from prescient.edge.scorecard import build_scorecard

    scores = [_score(True, True, 10.0, 0.8) for _ in range(150)]
    card = build_scorecard(source="x", scores=scores)
    assert card.sample_size_verdict == SampleSizeVerdict.MODERATE
