from __future__ import annotations

import hashlib
from typing import Protocol

from compass.research.edge.models import EventContext, Prediction, PredictionDirection


class Strategy(Protocol):
    def predict(self, context: EventContext) -> Prediction: ...


class AlwaysUpStrategy:
    source = "always_up"

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.UP,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
        )


class CoinFlipStrategy:
    source = "coin_flip"

    def predict(self, context: EventContext) -> Prediction:
        seed = f"{context.ticker}:{context.as_of_date.isoformat()}"
        digest = hashlib.sha256(seed.encode()).hexdigest()
        direction = (
            PredictionDirection.UP
            if int(digest, 16) % 2 == 0
            else PredictionDirection.DOWN
        )
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=direction,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
        )


class ReactionAwarePeerStrategy:
    source = "reaction_aware_peer"

    def predict(self, context: EventContext) -> Prediction:
        surprises = list(context.peer_eps_surprises.values())
        reactions = list(context.peer_stock_reactions.values())
        if not surprises:
            return Prediction(
                ticker=context.ticker,
                as_of_date=context.as_of_date,
                direction=PredictionDirection.NONE,
                predicted_move_pct=0.0,
                confidence=0.0,
                source=self.source,
            )
        beat_score = sum(surprises) / len(surprises)
        reaction_score = sum(reactions) / len(reactions) if reactions else 0.0
        direction = PredictionDirection.UP if beat_score > 0 else PredictionDirection.DOWN
        move = (abs(beat_score) + abs(reaction_score)) / 2.0
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=direction,
            predicted_move_pct=move if direction == PredictionDirection.UP else -move,
            confidence=max(0.0, min(0.9, 0.4 + reaction_score / 20.0)),
            source=self.source,
        )


class VolRampStrategy:
    source = "vol_ramp"
    exits_before_event = True

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
            buy_vol_ramp=True,
        )


class ShortVolStrategy:
    source = "short_vol"

    def predict(self, context: EventContext) -> Prediction:
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=PredictionDirection.NONE,
            predicted_move_pct=0.0,
            confidence=0.5,
            source=self.source,
            sell_straddle=True,
        )
