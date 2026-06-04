from __future__ import annotations

from prescient.signal.models import PeerResult, StrategyThesis, ThemeConfig, ThesisStatus
from prescient.signal.strategy_types import (
    DEFAULT_STRATEGY_TYPE,
    StrategySupportStatus,
    StrategyType,
    coerce_strategy_type,
    get_strategy_metadata,
)


DEFAULT_MINIMUM_PEER_COUNT = 3


def build_strategy_thesis(
    target: str,
    theme: ThemeConfig,
    peer_results: list[PeerResult],
    minimum_peer_count: int = DEFAULT_MINIMUM_PEER_COUNT,
    strategy_type: StrategyType | str = DEFAULT_STRATEGY_TYPE,
) -> StrategyThesis:
    """Build a deterministic bullish peer read-through thesis from structured inputs."""

    normalized_target = target.strip().upper()
    selected_strategy_type = coerce_strategy_type(strategy_type)
    strategy_metadata = get_strategy_metadata(selected_strategy_type)

    if strategy_metadata.status != StrategySupportStatus.ACTIVE:
        return StrategyThesis(
            target=normalized_target,
            theme=theme.name,
            strategy_type=selected_strategy_type,
            direction=strategy_metadata.direction,
            status=ThesisStatus.UNSUPPORTED_STRATEGY,
            reported_peers=[],
            positive_peer_count=0,
            minimum_peer_count=minimum_peer_count,
            shared_drivers=theme.drivers,
            reason=(
                f"Strategy {selected_strategy_type.value} is planned but not executable "
                "in the MVP."
            ),
        )

    if normalized_target not in theme.tickers:
        return StrategyThesis(
            target=normalized_target,
            theme=theme.name,
            strategy_type=selected_strategy_type,
            direction=strategy_metadata.direction,
            status=ThesisStatus.INVALID_THEME,
            reported_peers=[],
            positive_peer_count=0,
            minimum_peer_count=minimum_peer_count,
            shared_drivers=theme.drivers,
            reason=f"Target {normalized_target} is not configured in theme {theme.name}.",
        )

    same_theme_peers = _same_theme_peers(normalized_target, theme, peer_results)
    positive_peers = [peer for peer in same_theme_peers if _has_positive_readthrough_evidence(peer)]

    if len(positive_peers) < minimum_peer_count:
        return StrategyThesis(
            target=normalized_target,
            theme=theme.name,
            strategy_type=selected_strategy_type,
            direction=strategy_metadata.direction,
            status=ThesisStatus.INSUFFICIENT_PEER_CONTEXT,
            reported_peers=[peer.ticker for peer in same_theme_peers],
            positive_peer_count=len(positive_peers),
            minimum_peer_count=minimum_peer_count,
            shared_drivers=theme.drivers,
            reason=(
                f"Only {len(positive_peers)} positive peer result available; "
                f"{minimum_peer_count} are required for a strategy thesis."
            ),
        )

    if not theme.drivers or not any(peer.theme_driver_signal == "positive" for peer in positive_peers):
        return StrategyThesis(
            target=normalized_target,
            theme=theme.name,
            strategy_type=selected_strategy_type,
            direction=strategy_metadata.direction,
            status=ThesisStatus.MISSING_DRIVER_EVIDENCE,
            reported_peers=[peer.ticker for peer in same_theme_peers],
            positive_peer_count=len(positive_peers),
            minimum_peer_count=minimum_peer_count,
            shared_drivers=theme.drivers,
            reason=(
                f"Peer results are positive, but no structured theme-driver evidence "
                f"supports the {theme.name} read-through thesis."
            ),
        )

    return StrategyThesis(
        target=normalized_target,
        theme=theme.name,
        strategy_type=selected_strategy_type,
        direction=strategy_metadata.direction,
        status=ThesisStatus.VALID,
        reported_peers=[peer.ticker for peer in same_theme_peers],
        positive_peer_count=len(positive_peers),
        minimum_peer_count=minimum_peer_count,
        shared_drivers=theme.drivers,
        reason=(
            f"Bullish peer read-through thesis: {len(positive_peers)} peers in {theme.name} "
            "reported positive earnings or theme-driver evidence around shared drivers."
        ),
    )


def _same_theme_peers(
    target: str,
    theme: ThemeConfig,
    peer_results: list[PeerResult],
) -> list[PeerResult]:
    seen: set[str] = set()
    peers: list[PeerResult] = []

    for peer in peer_results:
        if peer.ticker == target or peer.ticker not in theme.tickers or peer.ticker in seen:
            continue
        seen.add(peer.ticker)
        peers.append(peer)

    return peers


def _has_positive_readthrough_evidence(peer: PeerResult) -> bool:
    return (
        _beat(peer.earnings_event.eps_actual, peer.earnings_event.eps_estimate)
        or _beat(peer.earnings_event.revenue_actual, peer.earnings_event.revenue_estimate)
        or peer.guidance_signal == "positive"
        or peer.theme_driver_signal == "positive"
    )


def _beat(actual: float | None, estimate: float | None) -> bool:
    return actual is not None and estimate is not None and actual > estimate
