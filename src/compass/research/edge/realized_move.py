from __future__ import annotations

from datetime import date

from compass.research.edge.models import DailyBar, RealizedMove


def compute_realized_move(
    *,
    ticker: str,
    as_of_date: date,
    bars: list[DailyBar],
    horizon_days: int,
) -> RealizedMove | None:
    if horizon_days <= 0:
        return None
    ordered = sorted(bars, key=lambda bar: bar.trading_date)
    as_of_index = next(
        (index for index, bar in enumerate(ordered) if bar.trading_date == as_of_date),
        None,
    )
    if as_of_index is None or as_of_index + horizon_days >= len(ordered):
        return None
    before = ordered[as_of_index].close
    after = ordered[as_of_index + horizon_days].close
    if before is None or after is None or before <= 0:
        return None
    return RealizedMove(
        ticker=ticker,
        pre_report_close=before,
        post_report_close=after,
        realized_move_pct=((after - before) / before) * 100.0,
    )
