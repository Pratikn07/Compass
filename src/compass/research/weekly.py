from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from compass.research.edge.models import EventContext
from compass.research.edge.runner import run_edge_backtest
from compass.research.edge.strategy import (
    AlwaysUpStrategy,
    CoinFlipStrategy,
    ReactionAwarePeerStrategy,
    ShortVolStrategy,
    VolRampStrategy,
)


class ResearchRepository(Protocol):
    def edge_context_snapshots(self) -> list[dict]: ...


def load_edge_contexts(repository: ResearchRepository) -> tuple[list[EventContext], int]:
    contexts = []
    invalid = 0
    for snapshot in repository.edge_context_snapshots():
        payload = snapshot.get("payload") or {}
        context_payload = payload.get("event_context")
        if not isinstance(context_payload, dict):
            continue
        try:
            contexts.append(EventContext.model_validate(context_payload))
        except ValidationError:
            invalid += 1
    return contexts, invalid


def run_weekly_edge_report(repository: ResearchRepository) -> dict:
    contexts, invalid = load_edge_contexts(repository)
    result = run_edge_backtest(
        contexts=contexts,
        strategies=[
            ReactionAwarePeerStrategy(),
            ShortVolStrategy(),
            VolRampStrategy(),
            CoinFlipStrategy(),
            AlwaysUpStrategy(),
        ],
    )
    payload = result.model_dump(mode="json")
    payload.update(
        {
            "contexts_evaluated": len(contexts),
            "invalid_contexts_skipped": invalid,
            "execution_enabled": False,
        }
    )
    return payload
