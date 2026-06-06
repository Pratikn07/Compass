"""Live Alpaca SDK reader callables for the market-data adapter.

Lives in the orchestration layer (not prescient.data) so the data package stays
free of execution/SDK imports. Builds read-only Alpaca clients and binds them to
the reader-callable contract that AlpacaMarketDataAdapter expects. Read-only: no
broker execution adapter is constructed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from prescient.data.alpaca_market import (
    DailyBarsReader,
    HistoricalOptionReader,
    HistoricalOptionRow,
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


def build_historical_option_reader(
    *, api_key_id: str, api_secret_key: str
) -> HistoricalOptionReader:
    """Build a live reader callable for as-of historical option straddles (read-only).

    Lists EXPIRED contracts (both CALL and PUT) in the expiration window, then batch
    fetches daily option bars and takes the bar on/just-before as_of_date for each
    contract, returning normalized HistoricalOptionRow rows (close from the bar)."""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest

    option_data = OptionHistoricalDataClient(api_key_id, api_secret_key)
    trading = TradingClient(api_key_id, api_secret_key, paper=True)

    def historical_option_reader(
        *,
        underlying_symbol: str,
        as_of_date: date,
        earnings_date: date,
        max_expiration_date: date,
    ) -> list[HistoricalOptionRow]:
        contracts: list[Any] = []
        for opt_type in ("call", "put"):
            resp = trading.get_option_contracts(
                GetOptionContractsRequest(
                    underlying_symbols=[underlying_symbol],
                    status="inactive",
                    type=opt_type,
                    expiration_date_gte=earnings_date,
                    expiration_date_lte=max_expiration_date,
                    limit=1000,
                )
            )
            contracts.extend(getattr(resp, "option_contracts", []) or [])
        if not contracts:
            return []

        symbol_meta: dict[str, tuple[float, Any, str, int | None]] = {}
        for c in contracts:
            type_text = str(c.type).lower()
            if "call" in type_text:
                opt_type = "CALL"
            elif "put" in type_text:
                opt_type = "PUT"
            else:
                # Fail loud: a silent misclassification would make every straddle
                # fail to pair. Surfacing the unexpected SDK value is the honest
                # move.
                raise ValueError(
                    f"Unrecognized option type from Alpaca: {c.type!r}"
                )
            symbol_meta[c.symbol] = (
                float(c.strike_price),
                c.expiration_date,
                opt_type,
                int(c.open_interest) if c.open_interest is not None else None,
            )

        start = (
            datetime(as_of_date.year, as_of_date.month, as_of_date.day)
            - timedelta(days=4)
        )
        end = (
            datetime(as_of_date.year, as_of_date.month, as_of_date.day)
            + timedelta(days=1)
        )
        bars_resp = option_data.get_option_bars(
            OptionBarsRequest(
                symbol_or_symbols=list(symbol_meta.keys()),
                start=start,
                end=end,
                timeframe=TimeFrame.Day,
            )
        )
        bars_by_symbol = getattr(bars_resp, "data", {}) or {}

        rows: list[HistoricalOptionRow] = []
        for symbol, (
            strike,
            expiration,
            opt_type,
            open_interest,
        ) in symbol_meta.items():
            # Sort ascending so the LAST bar with date <= as_of is the
            # on/just-before bar, even if the SDK ever returns bars out of order
            # (live data we cannot unit-test; cheap insurance against a
            # silently-stale close price).
            bars = sorted(
                bars_by_symbol.get(symbol, []), key=lambda b: b.timestamp
            )
            as_of_bar = None
            for bar in bars:
                if bar.timestamp.date() <= as_of_date:
                    as_of_bar = bar
            rows.append(
                HistoricalOptionRow(
                    contract_symbol=symbol,
                    strike=strike,
                    expiration_date=expiration,
                    option_type=opt_type,
                    close=getattr(as_of_bar, "close", None),
                    open_interest=open_interest,
                )
            )
        return rows

    return historical_option_reader
