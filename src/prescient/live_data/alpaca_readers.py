"""Live Alpaca SDK reader callables for the market-data adapter.

Lives in the orchestration layer (not prescient.data) so the data package stays
free of execution/SDK imports. Builds read-only Alpaca clients and binds them to
the reader-callable contract that AlpacaMarketDataAdapter expects. Read-only: no
broker execution adapter is constructed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from prescient.data.alpaca_market import (
    DailyBarsReader,
    OptionChainEntry,
    OptionChainReader,
)


def build_alpaca_sdk_readers(
    *, api_key_id: str, api_secret_key: str
) -> tuple[OptionChainReader, DailyBarsReader]:
    """Build live reader callables backed by the Alpaca SDK (read-only clients)."""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest

    option_data = OptionHistoricalDataClient(api_key_id, api_secret_key)
    stock_data = StockHistoricalDataClient(api_key_id, api_secret_key)
    trading = TradingClient(api_key_id, api_secret_key, paper=True)

    def option_chain_reader(
        *, underlying_symbol: str, feed: str
    ) -> list[OptionChainEntry]:
        contracts_resp = trading.get_option_contracts(
            GetOptionContractsRequest(
                underlying_symbols=[underlying_symbol],
                status="active",
                type="call",
                limit=1000,
            )
        )
        contracts = getattr(contracts_resp, "option_contracts", []) or []

        chain = option_data.get_option_chain(
            OptionChainRequest(underlying_symbol=underlying_symbol, feed=feed)
        )

        entries: list[OptionChainEntry] = []
        for contract in contracts:
            snapshot = chain.get(contract.symbol) if hasattr(chain, "get") else None
            quote = getattr(snapshot, "latest_quote", None)
            entries.append(
                OptionChainEntry(
                    contract_symbol=contract.symbol,
                    strike_price=float(contract.strike_price),
                    expiration_date=contract.expiration_date,
                    option_type="CALL",
                    bid=getattr(quote, "bid_price", None),
                    ask=getattr(quote, "ask_price", None),
                    open_interest=(
                        int(contract.open_interest)
                        if contract.open_interest is not None
                        else None
                    ),
                )
            )
        return entries

    def daily_bars_reader(
        *, symbols: Sequence[str], start: date, end: date
    ) -> dict[str, list[dict[str, Any]]]:
        resp = stock_data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=list(symbols),
                start=datetime(start.year, start.month, start.day),
                end=datetime(end.year, end.month, end.day),
                timeframe=TimeFrame.Day,
            )
        )
        data = getattr(resp, "data", {}) or {}
        out: dict[str, list[dict[str, Any]]] = {}
        for symbol, bars in data.items():
            out[symbol] = [
                {
                    "trading_date": bar.timestamp.date(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": int(bar.volume) if bar.volume is not None else None,
                    "vwap": getattr(bar, "vwap", None),
                }
                for bar in bars
            ]
        return out

    return option_chain_reader, daily_bars_reader
