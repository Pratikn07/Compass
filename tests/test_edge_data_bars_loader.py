from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot


class FakeBarsAdapter:
    def __init__(self, data):
        self._data = data
        self.calls = []

    def get_daily_bars(self, *, symbols, start, end):
        self.calls.append({"symbols": list(symbols), "start": start, "end": end})
        return self._data


def test_load_daily_bars_passes_through_and_batches() -> None:
    from prescient.edge.data.bars_loader import load_daily_bars

    data = {"MU": [DailyBarSnapshot(ticker="MU", trading_date=date(2024, 6, 25), close=100.0)]}
    adapter = FakeBarsAdapter(data)
    out = load_daily_bars(
        adapter, tickers=["MU", "NVDA"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert out == data
    assert adapter.calls == [
        {"symbols": ["MU", "NVDA"], "start": date(2024, 1, 1), "end": date(2024, 12, 31)}
    ]
