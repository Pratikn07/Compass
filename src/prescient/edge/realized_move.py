from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.models import RealizedMove


def compute_realized_move(
    *,
    ticker: str,
    as_of_date: date,
    bars: list[DailyBarSnapshot],
    horizon_days: int,
) -> RealizedMove | None:
    """Signed % move from the as-of close to the close `horizon_days` trading
    days later. Returns None (skip) when required closes are absent.
    """
    if horizon_days <= 0:
        return None
    ordered = sorted(bars, key=lambda b: b.trading_date)
    as_of_index: int | None = None
    for index, bar in enumerate(ordered):
        if bar.trading_date == as_of_date:
            as_of_index = index
            break
    if as_of_index is None:
        return None
    exit_index = as_of_index + horizon_days
    if exit_index >= len(ordered):
        return None
    pre = ordered[as_of_index].close
    post = ordered[exit_index].close
    if pre is None or post is None or pre <= 0:
        return None
    return RealizedMove(
        ticker=ticker,
        pre_report_close=pre,
        post_report_close=post,
        realized_move_pct=((post - pre) / pre) * 100.0,
    )
