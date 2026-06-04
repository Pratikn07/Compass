"""Event-driven trigger normalization and local classification."""

from prescient.events.classifier import classify_event, normalize_event
from prescient.events.models import (
    EventClassification,
    EventImportance,
    EventSourceType,
    EventTriggerResult,
    FastPollPlan,
    MarketEventType,
    NormalizedEvent,
)
from prescient.events.runner import handle_event_trigger

__all__ = [
    "EventClassification",
    "EventImportance",
    "EventSourceType",
    "EventTriggerResult",
    "FastPollPlan",
    "MarketEventType",
    "NormalizedEvent",
    "classify_event",
    "handle_event_trigger",
    "normalize_event",
]
