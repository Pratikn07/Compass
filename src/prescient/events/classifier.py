from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from datetime import datetime

from prescient.events.models import (
    EventClassification,
    EventImportance,
    EventSourceType,
    MarketEventType,
    NormalizedEvent,
    PayloadValue,
)
from prescient.signal.models import StrategyUniverse


_CANDIDATE_REVIEW_EVENTS = {
    MarketEventType.EARNINGS_RESULT,
    MarketEventType.GUIDANCE_UPDATE,
}
_STRATEGY_REFRESH_EVENTS = {
    MarketEventType.MAJOR_NEWS,
    MarketEventType.PRICE_MOVE,
    MarketEventType.VOLUME_SPIKE,
    MarketEventType.OPTIONS_LIQUIDITY_CHANGE,
}


def normalize_event(
    *,
    source_type: EventSourceType,
    event_type: MarketEventType,
    ticker: str | None,
    source_name: str,
    payload_summary: Mapping[str, PayloadValue] | None = None,
    event_time: datetime | None = None,
    received_time: datetime | None = None,
    event_id: str | None = None,
) -> NormalizedEvent:
    normalized_ticker = ticker.strip().upper() if ticker is not None and ticker.strip() else None
    cleaned_payload = _clean_payload_summary(payload_summary or {})
    fingerprint = _fingerprint(
        {
            "event_id": event_id,
            "event_time": event_time.isoformat() if event_time is not None else None,
            "event_type": event_type.value,
            "payload_summary": cleaned_payload,
            "source_name": source_name,
            "source_type": source_type.value,
            "ticker": normalized_ticker,
        }
    )

    return NormalizedEvent(
        fingerprint=fingerprint,
        source_type=source_type,
        event_type=event_type,
        ticker=normalized_ticker,
        source_name=source_name,
        payload_summary=cleaned_payload,
        event_time=event_time,
        received_time=received_time,
        event_id=event_id,
    )


def classify_event(
    event: NormalizedEvent,
    *,
    universe: StrategyUniverse,
    active_tickers: Collection[str] | None = None,
) -> EventClassification:
    if event.ticker is None:
        return _classification(
            event,
            theme=None,
            is_relevant=False,
            importance=EventImportance.IGNORED,
            reason="Event ticker is missing.",
        )

    if event.event_type == MarketEventType.UNSUPPORTED:
        return _classification(
            event,
            theme=None,
            is_relevant=False,
            importance=EventImportance.IGNORED,
            reason="Event type is unsupported.",
        )

    themes = universe.themes_for_ticker(event.ticker)
    if not themes:
        return _classification(
            event,
            theme=None,
            is_relevant=False,
            importance=EventImportance.IGNORED,
            reason="Event ticker is outside the configured strategy universe.",
        )

    theme_name = themes[0].name
    if active_tickers is not None and event.ticker not in _normalize_ticker_set(active_tickers):
        return _classification(
            event,
            theme=theme_name,
            is_relevant=True,
            importance=EventImportance.JOURNAL_ONLY,
            reason="Event ticker is relevant but not in the active event window.",
        )

    if event.event_type == MarketEventType.QUOTE:
        return _classification(
            event,
            theme=theme_name,
            is_relevant=True,
            importance=EventImportance.JOURNAL_ONLY,
            reason="Quote event is relevant but not important enough for strategy refresh.",
        )

    if event.event_type in _CANDIDATE_REVIEW_EVENTS:
        return _classification(
            event,
            theme=theme_name,
            is_relevant=True,
            importance=EventImportance.CANDIDATE_REVIEW,
            reason="Earnings or guidance event can materially affect candidate review.",
        )

    if event.event_type in _STRATEGY_REFRESH_EVENTS:
        return _classification(
            event,
            theme=theme_name,
            is_relevant=True,
            importance=EventImportance.STRATEGY_REFRESH,
            reason="Market event can materially affect deterministic strategy evaluation.",
        )

    return _classification(
        event,
        theme=theme_name,
        is_relevant=True,
        importance=EventImportance.JOURNAL_ONLY,
        reason="Event is relevant but has no strategy-refresh rule.",
    )


def _classification(
    event: NormalizedEvent,
    *,
    theme: str | None,
    is_relevant: bool,
    importance: EventImportance,
    reason: str,
    is_duplicate: bool = False,
) -> EventClassification:
    should_refresh = importance in {
        EventImportance.STRATEGY_REFRESH,
        EventImportance.CANDIDATE_REVIEW,
    } and not is_duplicate

    return EventClassification(
        fingerprint=event.fingerprint,
        source_type=event.source_type,
        event_type=event.event_type,
        ticker=event.ticker,
        theme=theme,
        is_relevant=is_relevant,
        importance=importance,
        reason=reason,
        should_refresh_strategy=should_refresh,
        claude_analysis_allowed=importance == EventImportance.CANDIDATE_REVIEW
        and not is_duplicate,
        is_duplicate=is_duplicate,
    )


def duplicate_classification(classification: EventClassification) -> EventClassification:
    return EventClassification(
        fingerprint=classification.fingerprint,
        source_type=classification.source_type,
        event_type=classification.event_type,
        ticker=classification.ticker,
        theme=classification.theme,
        is_relevant=classification.is_relevant,
        importance=classification.importance,
        reason="Duplicate event fingerprint was already processed.",
        should_refresh_strategy=False,
        claude_analysis_allowed=False,
        is_duplicate=True,
    )


def _clean_payload_summary(
    payload_summary: Mapping[str, PayloadValue],
) -> dict[str, PayloadValue]:
    cleaned: dict[str, PayloadValue] = {}
    for key, value in payload_summary.items():
        normalized_key = key.strip()
        if "raw" in normalized_key.lower():
            raise ValueError("Event payload summary must not include raw payload fields.")
        cleaned[normalized_key] = value
    return cleaned


def _fingerprint(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_ticker_set(tickers: Collection[str]) -> set[str]:
    return {ticker.strip().upper() for ticker in tickers if ticker.strip()}
