from __future__ import annotations

import hashlib
from typing import Protocol

from prescient.edge.models import EventContext, Prediction, PredictionDirection


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
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
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
    """Owner thesis: peers that already beat lean the target bullish, but a weak
    peer STOCK reaction (good news already priced in) caps confidence."""

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
        direction = (
            PredictionDirection.UP if beat_score > 0 else PredictionDirection.DOWN
        )
        # predicted move blends beat strength and how much peers' stocks moved
        predicted_move_pct = (abs(beat_score) * 0.5) + (abs(reaction_score) * 0.5)
        if direction == PredictionDirection.DOWN:
            predicted_move_pct = -predicted_move_pct
        # confidence rises with reaction strength; weak reaction => low confidence
        confidence = max(0.0, min(0.9, 0.4 + (reaction_score / 20.0)))
        return Prediction(
            ticker=context.ticker,
            as_of_date=context.as_of_date,
            direction=direction,
            predicted_move_pct=predicted_move_pct,
            confidence=confidence,
            source=self.source,
        )


class ShortVolStrategy:
    """Non-directional: bets the realized move stays below the implied move, by
    SELLING the ATM straddle (defined-risk in the P&L model). It does not predict
    up/down; it always wants to sell vol when a straddle exists."""

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
