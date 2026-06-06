from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import AssembledEdgeDataset, EarningsAnnouncement
from prescient.edge.data.peer_signals import build_peer_signals
from prescient.edge.loader import PointInTimeDataset, build_event_context
from prescient.edge.models import OptionQuote


def assemble_edge_dataset(
    *,
    announcements: Sequence[EarningsAnnouncement],
    bars: dict[str, list[DailyBarSnapshot]],
    option_quotes: dict[str, list[OptionQuote]],
    target_tickers: Sequence[str],
    horizon_days: int,
    peer_window_days: int,
) -> AssembledEdgeDataset:
    """Assemble edge EventContexts (with peer signals) + a coverage summary.

    Network-free: operates on already-fetched announcements/bars/option_quotes so it
    is fully unit-testable. as_of_date = report_date - 1 day; peer signals are anchored
    to that same as_of_date so the no-lookahead filter aligns with the event anchor.

    Calls build_peer_signals once per target event with the full announcements list
    (O(n^2) in event count). Acceptable for offline, cached backtest assembly; if it
    ever becomes a bottleneck, pre-group announcements by time window.
    """
    dataset = PointInTimeDataset(bars=bars, option_quotes=option_quotes)
    targets = {t.strip().upper() for t in target_tickers}

    contexts: list[object] = []
    dropped = 0
    drop_reasons: dict[str, int] = {}
    total = 0

    for ann in announcements:
        if ann.ticker not in targets:
            continue
        total += 1
        # Anchor as_of to the last TRADING day on/before report_date - 1 calendar day.
        # A bare calendar -1 lands on weekends/holidays, where compute_realized_move
        # (which needs a bar dated exactly on as_of) returns None and silently drops
        # Monday/post-holiday reporters. Derive the real prior trading day from bars.
        calendar_prior = ann.report_date - timedelta(days=1)
        visible = dataset.bars_as_of(ann.ticker, as_of_date=calendar_prior)
        if not visible:
            dropped += 1
            drop_reasons["no_prior_bar"] = drop_reasons.get("no_prior_bar", 0) + 1
            continue
        as_of_date = visible[-1].trading_date
        ctx = build_event_context(
            dataset=dataset,
            ticker=ann.ticker,
            earnings_date=ann.report_date,
            as_of_date=as_of_date,
            horizon_days=horizon_days,
        )
        if ctx is None:
            dropped += 1
            drop_reasons["no_event_context"] = drop_reasons.get("no_event_context", 0) + 1
            continue
        surprises, reactions = build_peer_signals(
            target=ann.ticker,
            target_as_of_date=as_of_date,
            announcements=list(announcements),
            bars=bars,
            peer_window_days=peer_window_days,
        )
        contexts.append(
            ctx.model_copy(
                update={"peer_eps_surprises": surprises, "peer_stock_reactions": reactions}
            )
        )

    return AssembledEdgeDataset(
        event_contexts=contexts,
        dataset=dataset,
        events_total=total,
        events_dropped=dropped,
        drop_reasons=drop_reasons,
        errors=[],
    )
