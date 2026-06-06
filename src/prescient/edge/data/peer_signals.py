from __future__ import annotations

from datetime import date, timedelta

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement


def _surprise_pct(ann: EarningsAnnouncement) -> float | None:
    if ann.surprise_pct is not None:
        return ann.surprise_pct
    if ann.eps_estimate is not None and ann.eps_actual is not None and ann.eps_estimate != 0:
        return ((ann.eps_actual - ann.eps_estimate) / abs(ann.eps_estimate)) * 100.0
    return None


def _reaction_pct(bars: list[DailyBarSnapshot], report_date: date) -> float | None:
    """Close the trading day before report -> close the trading day after."""
    ordered = sorted(bars, key=lambda b: b.trading_date)
    before = [b for b in ordered if b.trading_date < report_date and b.close is not None]
    after = [b for b in ordered if b.trading_date > report_date and b.close is not None]
    if not before or not after:
        return None
    pre = before[-1].close
    post = after[0].close
    if pre is None or post is None or pre <= 0:
        return None
    return ((post - pre) / pre) * 100.0


def build_peer_signals(
    *,
    target: str,
    target_as_of_date: date,
    announcements: list[EarningsAnnouncement],
    bars: dict[str, list[DailyBarSnapshot]],
    peer_window_days: int,
) -> tuple[dict[str, float], dict[str, float]]:
    target = target.strip().upper()
    window_start = target_as_of_date - timedelta(days=peer_window_days)
    surprises: dict[str, float] = {}
    reactions: dict[str, float] = {}
    seen: set[str] = set()

    for ann in announcements:
        peer = ann.ticker
        if peer == target or peer in seen:
            continue
        # No-lookahead: peer must have reported strictly before the target's anchor,
        # and within the trailing window.
        if not (window_start <= ann.report_date < target_as_of_date):
            continue
        surprise = _surprise_pct(ann)
        if surprise is None:
            continue
        seen.add(peer)
        surprises[peer] = surprise
        reaction = _reaction_pct(bars.get(peer, []), ann.report_date)
        if reaction is not None:
            reactions[peer] = reaction

    return surprises, reactions
