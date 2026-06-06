"""Read-only Alpaca market-data adapter (R5C.2).

Sources option-chain snapshots and daily stock bars for the live-data pipeline.
It must NOT import or construct broker execution adapters — it uses Alpaca
market-data / contract-metadata reads only.

Design: the adapter depends on injected reader callables (option chain, daily
bars). In production a factory wires them to real Alpaca SDK clients; tests inject
fakes so no live SDK call happens in CI. Provider failures become DataProviderError
values via an injected error sink; the chain reader returns [] on failure so a bad
options feed degrades (engine then rejects as OPTIONS_TOO_ILLIQUID) rather than
crashing the run.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from prescient.edge.models import OptionQuote

from prescient.data.models import (
    DailyBarSnapshot,
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
)
from prescient.signal.models import OptionContractSnapshot

Feed = Literal["indicative", "opra"]


@dataclass(frozen=True)
class OptionChainEntry:
    """Normalized option-chain row (contract metadata merged with latest quote)."""

    contract_symbol: str
    strike_price: float
    expiration_date: date
    option_type: Literal["CALL", "PUT"]
    bid: float | None
    ask: float | None
    open_interest: int | None


OptionChainReader = Callable[..., list[OptionChainEntry]]
DailyBarsReader = Callable[..., dict[str, list[dict[str, Any]]]]
ErrorSink = Callable[[DataProviderError], None]


@dataclass(frozen=True)
class HistoricalOptionRow:
    """A past option contract + its close on a specific as-of date (from option bars)."""

    contract_symbol: str
    strike: float
    expiration_date: date
    option_type: Literal["CALL", "PUT"]
    close: float | None
    open_interest: int | None = None


HistoricalOptionReader = Callable[..., list["HistoricalOptionRow"]]


class AlpacaMarketDataAdapter:
    def __init__(
        self,
        *,
        option_chain_reader: OptionChainReader | None = None,
        daily_bars_reader: DailyBarsReader | None = None,
        historical_option_reader: "HistoricalOptionReader | None" = None,
        error_sink: ErrorSink | None = None,
    ) -> None:
        self._option_chain_reader = option_chain_reader
        self._daily_bars_reader = daily_bars_reader
        self._historical_option_reader = historical_option_reader
        self._errors: list[DataProviderError] = []
        self._error_sink = error_sink or self._errors.append

    @property
    def errors(self) -> list[DataProviderError]:
        return list(self._errors)

    def get_option_chain_snapshots(
        self,
        *,
        underlying_symbol: str,
        earnings_date: date,
        max_expiration_date: date,
        feed: Feed = "indicative",
        fetched_at: datetime | None = None,
    ) -> list[OptionContractSnapshot]:
        symbol = underlying_symbol.strip().upper()
        if self._option_chain_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca option-chain reader is not configured.",
                symbol=symbol,
            )
            return []

        try:
            entries = self._option_chain_reader(
                underlying_symbol=symbol, feed=feed
            )
        except Exception as exc:  # transport / auth / subscription failure
            self._record(*_classify(exc), symbol=symbol)
            return []

        in_window = [
            entry
            for entry in entries
            if entry.option_type == "CALL"
            and earnings_date <= entry.expiration_date <= max_expiration_date
        ]
        in_window.sort(
            key=lambda e: (e.expiration_date, e.strike_price, e.contract_symbol)
        )

        return [
            OptionContractSnapshot(
                ticker=symbol,
                option_type="CALL",
                expiration_date=entry.expiration_date,
                bid=entry.bid,
                ask=entry.ask,
                open_interest=entry.open_interest,
            )
            for entry in in_window
        ]

    def get_atm_option_quotes(
        self,
        *,
        underlying_symbol: str,
        quote_date: date,
        earnings_date: date,
        max_expiration_date: date,
        feed: Feed = "indicative",
    ) -> list["OptionQuote"]:
        """Return CALL and PUT quotes (with strikes) in the expiration window, as
        edge OptionQuotes stamped with quote_date. Strike-preserving and both
        types - unlike get_option_chain_snapshots which drops strike and keeps
        CALLs only. The edge import is local to keep prescient.data free of a
        module-load-time dependency on prescient.edge (one-way layering). Note: this returns ALL strikes in the expiration window (both CALL and PUT); the actual at-the-money selection happens downstream in the edge loader's _atm_quote, so callers receive the full chain to choose from."""
        from prescient.edge.models import OptionQuote

        symbol = underlying_symbol.strip().upper()
        if self._option_chain_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca option-chain reader is not configured.",
                symbol=symbol,
            )
            return []

        try:
            entries = self._option_chain_reader(
                underlying_symbol=symbol, feed=feed
            )
        except Exception as exc:
            self._record(*_classify(exc), symbol=symbol)
            return []

        return [
            OptionQuote(
                ticker=symbol,
                option_type=entry.option_type,
                strike=entry.strike_price,
                expiration_date=entry.expiration_date,
                quote_date=quote_date,
                bid=entry.bid,
                ask=entry.ask,
                open_interest=entry.open_interest,
            )
            for entry in entries
            if earnings_date <= entry.expiration_date <= max_expiration_date
        ]

    def get_historical_atm_straddle(
        self,
        *,
        underlying_symbol: str,
        as_of_date: date,
        underlying_price: float,
        earnings_date: date,
        max_expiration_date: date,
    ) -> list["OptionQuote"]:
        """Return the as-of ATM [call, put] straddle for a past earnings event, priced
        at each leg's bar close (history has no bid/ask; the spread cost is modeled in
        the P&L haircut, so close avoids double-counting). Returns [] on any missing
        piece (no contracts, only one leg, missing close) - skip, never guess. Strike
        is the one nearest underlying_price; ties resolve to the lower strike."""
        from prescient.edge.models import OptionQuote

        symbol = underlying_symbol.strip().upper()
        if self._historical_option_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca historical-option reader is not configured.",
                symbol=symbol,
            )
            return []
        try:
            rows = self._historical_option_reader(
                underlying_symbol=symbol,
                as_of_date=as_of_date,
                earnings_date=earnings_date,
                max_expiration_date=max_expiration_date,
            )
        except Exception as exc:
            self._record(*_classify(exc), symbol=symbol)
            return []

        in_window = [
            row
            for row in rows
            if earnings_date <= row.expiration_date <= max_expiration_date
            and row.close is not None
        ]
        calls = [r for r in in_window if r.option_type == "CALL"]
        puts = [r for r in in_window if r.option_type == "PUT"]
        if not calls or not puts:
            return []

        atm_strike = min(
            (r.strike for r in calls),
            key=lambda s: (abs(s - underlying_price), s),
        )
        call = next((r for r in calls if r.strike == atm_strike), None)
        put = next((r for r in puts if r.strike == atm_strike), None)
        if call is None or put is None:
            return []

        return [
            OptionQuote(
                ticker=symbol,
                option_type="CALL",
                strike=atm_strike,
                expiration_date=call.expiration_date,
                quote_date=as_of_date,
                bid=call.close,
                ask=call.close,
                open_interest=call.open_interest,
            ),
            OptionQuote(
                ticker=symbol,
                option_type="PUT",
                strike=atm_strike,
                expiration_date=put.expiration_date,
                quote_date=as_of_date,
                bid=put.close,
                ask=put.close,
                open_interest=put.open_interest,
            ),
        ]

    def get_daily_bars(
        self,
        *,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> dict[str, list[DailyBarSnapshot]]:
        normalized = [s.strip().upper() for s in symbols if s.strip()]
        if self._daily_bars_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca daily-bars reader is not configured.",
            )
            return {}

        try:
            raw = self._daily_bars_reader(symbols=normalized, start=start, end=end)
        except Exception as exc:
            self._record(*_classify(exc))
            return {}

        out: dict[str, list[DailyBarSnapshot]] = {}
        for ticker, rows in raw.items():
            out[ticker.strip().upper()] = [
                DailyBarSnapshot(
                    ticker=ticker,
                    trading_date=row["trading_date"],
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    volume=row.get("volume"),
                    vwap=row.get("vwap"),
                )
                for row in rows
            ]
        return out

    def _record(
        self,
        error_type: DataProviderErrorType,
        message: str,
        *,
        symbol: str | None = None,
    ) -> None:
        self._error_sink(
            DataProviderError(
                provider=DataProvider.ALPACA,
                error_type=error_type,
                message=message,
                symbol=symbol,
            )
        )


def _classify(exc: Exception) -> tuple[DataProviderErrorType, str]:
    """Map an Alpaca SDK/transport exception to a secret-safe error type+message."""
    text = str(exc)
    lowered = text.lower()
    if "403" in lowered or "subscription" in lowered or "forbidden" in lowered:
        return DataProviderErrorType.UNAUTHORIZED, "Alpaca subscription/auth error."
    if "401" in lowered or "unauthorized" in lowered or "api key" in lowered:
        return DataProviderErrorType.UNAUTHORIZED, "Alpaca authentication failed."
    if "429" in lowered or "rate limit" in lowered:
        return DataProviderErrorType.RATE_LIMITED, "Alpaca rate limit reached."
    if "timeout" in lowered or "timed out" in lowered:
        return DataProviderErrorType.TIMEOUT, "Alpaca request timed out."
    # Default: provider unavailable. Keep a short, non-sensitive marker only.
    return DataProviderErrorType.PROVIDER_UNAVAILABLE, "Alpaca provider unavailable."
