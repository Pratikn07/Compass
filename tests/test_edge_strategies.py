from __future__ import annotations

from datetime import date

from prescient.edge.models import EventContext, PredictionDirection


def _ctx(**overrides) -> EventContext:
    base = dict(
        ticker="MU",
        earnings_date=date(2024, 6, 26),
        as_of_date=date(2024, 6, 25),
        underlying_price=100.0,
        peer_eps_surprises={"NVDA": 10.0, "AMD": 3.0, "AVGO": 2.0},
        peer_stock_reactions={"NVDA": 6.0, "AMD": 1.0, "AVGO": -3.0},
    )
    base.update(overrides)
    return EventContext(**base)


def test_always_up_always_predicts_up_full_confidence_direction() -> None:
    from prescient.edge.strategy import AlwaysUpStrategy

    pred = AlwaysUpStrategy().predict(_ctx())
    assert pred.direction == PredictionDirection.UP
    assert pred.source == "always_up"


def test_coin_flip_is_deterministic_for_same_event() -> None:
    from prescient.edge.strategy import CoinFlipStrategy

    strat = CoinFlipStrategy()
    a = strat.predict(_ctx())
    b = strat.predict(_ctx())
    assert a.direction == b.direction
    assert a.direction in (PredictionDirection.UP, PredictionDirection.DOWN)
    assert a.source == "coin_flip"


def test_reaction_aware_peer_leans_up_but_caps_confidence_on_weak_reaction() -> None:
    from prescient.edge.strategy import ReactionAwarePeerStrategy

    pred = ReactionAwarePeerStrategy().predict(_ctx())
    # peers beat (avg +5%) so lean UP, but weak avg reaction (+1.33%) caps confidence
    assert pred.direction == PredictionDirection.UP
    assert pred.predicted_move_pct > 0
    assert pred.confidence < 0.7
    assert pred.source == "reaction_aware_peer"


def test_reaction_aware_peer_none_when_no_peers() -> None:
    from prescient.edge.strategy import ReactionAwarePeerStrategy

    pred = ReactionAwarePeerStrategy().predict(
        _ctx(peer_eps_surprises={}, peer_stock_reactions={})
    )
    assert pred.direction == PredictionDirection.NONE
    assert pred.confidence == 0.0
