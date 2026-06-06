"""Live-data assembly for the edge backtest harness.

See docs/superpowers/specs/2026-06-05-edge-live-data-assembly-design.md.
"""

from prescient.edge.data.assembler import assemble_edge_dataset
from prescient.edge.data.bars_loader import load_daily_bars
from prescient.edge.data.cache import JsonFileCache
from prescient.edge.data.earnings_history import (
    AlphaVantageEarningsHistoryAdapter,
    EarningsHistoryProvider,
)
from prescient.edge.data.models import AssembledEdgeDataset, EarningsAnnouncement
from prescient.edge.data.option_loader import load_option_quotes_for_events
from prescient.edge.data.peer_signals import build_peer_signals

__all__ = [
    "AlphaVantageEarningsHistoryAdapter",
    "AssembledEdgeDataset",
    "EarningsAnnouncement",
    "EarningsHistoryProvider",
    "JsonFileCache",
    "assemble_edge_dataset",
    "build_peer_signals",
    "load_daily_bars",
    "load_option_quotes_for_events",
]
