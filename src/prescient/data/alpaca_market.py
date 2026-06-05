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
from typing import Any, Literal

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


class AlpacaMarketDataAdapter:
    def __init__(
        self,
        *,
        option_chain_reader: OptionChainReader | None = None,
        daily_bars_reader: DailyBarsReader | None = None,
        error_sink: ErrorSink | None = None,
    ) -> None:
        self._option_chain_reader = option_chain_reader
        self._daily_bars_reader = daily_bars_reader
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
