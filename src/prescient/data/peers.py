from __future__ import annotations

from prescient.data.models import PeerListSnapshot
from prescient.signal.models import StrategyUniverse


def filter_peers_to_universe(
    snapshot: PeerListSnapshot,
    universe: StrategyUniverse,
) -> PeerListSnapshot:
    return snapshot.model_copy(
        update={
            "peers": [
                peer for peer in snapshot.peers if universe.contains_ticker(peer)
            ]
        }
    )


def filter_peers_to_theme(
    snapshot: PeerListSnapshot,
    universe: StrategyUniverse,
    theme_name: str,
) -> PeerListSnapshot:
    theme = universe.get_theme(theme_name)
    configured_tickers = set(theme.tickers)
    return snapshot.model_copy(
        update={
            "peers": [
                peer for peer in snapshot.peers if peer in configured_tickers
            ]
        }
    )
