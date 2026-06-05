from __future__ import annotations

from datetime import date
from typing import Any

from prescient.data.alpaca_market import (
    AlpacaMarketDataAdapter,
    OptionChainEntry,
)
from prescient.data.models import DataProvider, DataProviderErrorType


def _entry(
    *,
    contract_symbol: str,
    strike: float,
    expiration: date,
    bid: float | None,
    ask: float | None,
    open_interest: int | None,
) -> OptionChainEntry:
    return OptionChainEntry(
        contract_symbol=contract_symbol,
        strike_price=strike,
        expiration_date=expiration,
        option_type="CALL",
        bid=bid,
        ask=ask,
        open_interest=open_interest,
    )


class _FakeOptionReader:
    def __init__(self, entries: list[OptionChainEntry] | Exception) -> None:
        self.entries = entries
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, underlying_symbol: str, feed: str) -> list[OptionChainEntry]:
        self.calls.append({"underlying_symbol": underlying_symbol, "feed": feed})
        if isinstance(self.entries, Exception):
            raise self.entries
        return self.entries


def test_option_chain_filters_expirations_and_sorts_deterministically() -> None:
    reader = _FakeOptionReader(
        [
            _entry(contract_symbol="NVDA260619C", strike=140.0,
                   expiration=date(2026, 6, 19), bid=5.0, ask=5.2, open_interest=100),
            _entry(contract_symbol="NVDA260612C130", strike=130.0,
                   expiration=date(2026, 6, 12), bid=8.0, ask=8.3, open_interest=200),
            _entry(contract_symbol="NVDA260612C135", strike=135.0,
                   expiration=date(2026, 6, 12), bid=6.0, ask=6.2, open_interest=150),
            # outside window — must be excluded
            _entry(contract_symbol="NVDA260720C", strike=140.0,
                   expiration=date(2026, 7, 20), bid=9.0, ask=9.4, open_interest=50),
        ]
    )
    adapter = AlpacaMarketDataAdapter(option_chain_reader=reader)

    snaps = adapter.get_option_chain_snapshots(
        underlying_symbol="nvda",
        earnings_date=date(2026, 6, 11),
        max_expiration_date=date(2026, 6, 30),
    )

    # window: 2026-06-11 .. 2026-06-30 -> excludes the 07-20 contract
    assert [s.expiration_date for s in snaps] == [
        date(2026, 6, 12), date(2026, 6, 12), date(2026, 6, 19),
    ]
    # within same expiration, sorted by strike: 130 then 135
    assert snaps[0].bid == 8.0 and snaps[1].bid == 6.0
    assert all(s.ticker == "NVDA" for s in snaps)
    assert all(s.option_type == "CALL" for s in snaps)
    assert reader.calls[0]["feed"] == "indicative"


def test_option_chain_missing_quote_or_oi_still_emitted_as_audit_snapshot() -> None:
    reader = _FakeOptionReader(
        [
            _entry(contract_symbol="NVDA260612C", strike=130.0,
                   expiration=date(2026, 6, 12), bid=None, ask=None, open_interest=None),
        ]
    )
    adapter = AlpacaMarketDataAdapter(option_chain_reader=reader)
    snaps = adapter.get_option_chain_snapshots(
        underlying_symbol="NVDA",
        earnings_date=date(2026, 6, 11),
        max_expiration_date=date(2026, 6, 30),
    )
    assert len(snaps) == 1
    assert snaps[0].bid is None and snaps[0].ask is None
    assert snaps[0].open_interest is None


def test_option_chain_provider_failure_returns_empty_and_records_error() -> None:
    reader = _FakeOptionReader(RuntimeError("403 subscription required"))
    errors: list[Any] = []
    adapter = AlpacaMarketDataAdapter(
        option_chain_reader=reader, error_sink=errors.append
    )
    snaps = adapter.get_option_chain_snapshots(
        underlying_symbol="NVDA",
        earnings_date=date(2026, 6, 11),
        max_expiration_date=date(2026, 6, 30),
    )
    assert snaps == []
    assert len(errors) == 1
    assert errors[0].provider == DataProvider.ALPACA
    assert errors[0].error_type in {
        DataProviderErrorType.PROVIDER_UNAVAILABLE,
        DataProviderErrorType.UNAUTHORIZED,
    }
    # secret-safe: no raw exception internals leaking a key
    assert "403 subscription required" in errors[0].message or errors[0].message


def test_daily_bars_maps_and_normalizes() -> None:
    def bars_reader(*, symbols, start, end):
        return {
            "nvda": [
                {"trading_date": date(2026, 6, 10), "open": 1.0, "high": 2.0,
                 "low": 0.5, "close": 1.5, "volume": 1000, "vwap": 1.4},
            ]
        }

    adapter = AlpacaMarketDataAdapter(daily_bars_reader=bars_reader)
    out = adapter.get_daily_bars(
        symbols=["nvda"], start=date(2026, 6, 1), end=date(2026, 6, 10)
    )
    assert "NVDA" in out
    bar = out["NVDA"][0]
    assert bar.close == 1.5 and bar.volume == 1000
    assert bar.provider == DataProvider.ALPACA
