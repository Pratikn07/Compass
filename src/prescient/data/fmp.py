from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

import httpx

from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    PeerListResult,
    PeerListSnapshot,
    TranscriptResult,
    TranscriptSnapshot,
)


_STOCK_PEERS_ENDPOINT = "/stock-peers"
_BULK_PEERS_ENDPOINT = "/peers-bulk"


class SyncHttpResponse(Protocol):
    status_code: int

    def json(self) -> Any:
        ...


class SyncHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> SyncHttpResponse:
        ...


class _DefaultHttpClient:
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> SyncHttpResponse:
        return httpx.get(url, params=params, timeout=timeout)


class FmpStockPeersAdapter:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://financialmodelingprep.com/stable",
        timeout_seconds: float = 10.0,
        http_client: SyncHttpClient | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client or _DefaultHttpClient()

    def get_stock_peers(
        self,
        ticker: str,
        *,
        fetched_at: datetime | None = None,
    ) -> PeerListResult:
        symbol = _normalize_symbol(ticker)
        endpoint = _STOCK_PEERS_ENDPOINT
        if not self._api_key:
            return _error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP API key is required for stock peers.",
            )

        response = self._get(
            endpoint,
            params={"symbol": symbol, "apikey": self._api_key},
            symbol=symbol,
        )
        if isinstance(response, PeerListResult):
            return response

        return _parse_peer_response(
            response,
            endpoint=endpoint,
            requested_symbol=symbol,
            fetched_at=fetched_at,
        )

    def get_bulk_stock_peers(
        self,
        *,
        fetched_at: datetime | None = None,
    ) -> PeerListResult:
        endpoint = _BULK_PEERS_ENDPOINT
        if not self._api_key:
            return _error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=endpoint,
                symbol=None,
                message="FMP API key is required for bulk stock peers.",
            )

        response = self._get(
            endpoint,
            params={"apikey": self._api_key},
            symbol=None,
        )
        if isinstance(response, PeerListResult):
            return response

        return _parse_peer_response(
            response,
            endpoint=endpoint,
            requested_symbol=None,
            fetched_at=fetched_at,
        )

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
        symbol: str | None,
    ) -> SyncHttpResponse | PeerListResult:
        try:
            response = self._http_client.get(
                f"{self._base_url}{endpoint}",
                params=params,
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException):
            return _error_result(
                DataProviderErrorType.TIMEOUT,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP stock peers request timed out.",
            )
        except httpx.HTTPError:
            return _error_result(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP stock peers provider is unavailable.",
            )

        status_error = _status_error(response.status_code)
        if status_error is not None:
            return _error_result(
                status_error,
                endpoint=endpoint,
                symbol=symbol,
                status_code=response.status_code,
                message=_message_for_status_error(status_error),
            )

        return response


def _parse_peer_response(
    response: SyncHttpResponse,
    *,
    endpoint: str,
    requested_symbol: str | None,
    fetched_at: datetime | None,
) -> PeerListResult:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return _error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=endpoint,
            symbol=requested_symbol,
            message="FMP stock peers response was not valid JSON.",
        )

    entries = _payload_entries(payload)
    if not entries:
        return _error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            endpoint=endpoint,
            symbol=requested_symbol,
            message="FMP stock peers response was empty.",
        )

    snapshots: list[PeerListSnapshot] = []
    for entry in entries:
        snapshot = _snapshot_from_entry(
            entry,
            endpoint=endpoint,
            requested_symbol=requested_symbol,
            fetched_at=fetched_at,
        )
        if snapshot is None:
            return _error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=endpoint,
                symbol=requested_symbol,
                message="FMP stock peers response had an unsupported shape.",
            )
        snapshots.append(snapshot)

    return PeerListResult(snapshots=snapshots, errors=[])


def _payload_entries(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return [payload]
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, Mapping)]
    return []


def _snapshot_from_entry(
    entry: Mapping[str, Any],
    *,
    endpoint: str,
    requested_symbol: str | None,
    fetched_at: datetime | None,
) -> PeerListSnapshot | None:
    raw_symbol = entry.get("symbol", requested_symbol)
    if not isinstance(raw_symbol, str) or not raw_symbol.strip():
        return None

    ticker = _normalize_symbol(raw_symbol)
    raw_peers = _raw_peers(entry)
    if raw_peers is None:
        return None

    return PeerListSnapshot(
        ticker=ticker,
        peers=_normalize_peers(raw_peers, target=ticker),
        provider=DataProvider.FMP,
        source_endpoint=endpoint,
        provider_notes=[],
        fetched_at=fetched_at,
    )


def _raw_peers(entry: Mapping[str, Any]) -> Sequence[Any] | None:
    for key in ["peers", "peersList", "peerList"]:
        value = entry.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return value.split(",")
    return None


def _normalize_peers(values: Sequence[Any], *, target: str) -> list[str]:
    peers: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        peer = _normalize_symbol(value)
        if peer and peer != target and peer not in peers:
            peers.append(peer)
    return peers


def _normalize_symbol(value: str) -> str:
    return value.strip().upper()


def _status_error(status_code: int) -> DataProviderErrorType | None:
    if status_code in {401, 403}:
        return DataProviderErrorType.UNAUTHORIZED
    if status_code == 404:
        return DataProviderErrorType.UNSUPPORTED_SYMBOL
    if status_code == 429:
        return DataProviderErrorType.RATE_LIMITED
    if status_code >= 500:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    if status_code >= 400:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    return None


def _message_for_status_error(error_type: DataProviderErrorType) -> str:
    messages = {
        DataProviderErrorType.UNAUTHORIZED: "FMP stock peers access is unauthorized.",
        DataProviderErrorType.RATE_LIMITED: "FMP stock peers request was rate limited.",
        DataProviderErrorType.UNSUPPORTED_SYMBOL: "FMP stock peers symbol is unsupported.",
        DataProviderErrorType.PROVIDER_UNAVAILABLE: (
            "FMP stock peers provider is unavailable."
        ),
    }
    return messages.get(error_type, "FMP stock peers request failed.")


def _error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> PeerListResult:
    return PeerListResult(
        snapshots=[],
        errors=[
            DataProviderError(
                provider=DataProvider.FMP,
                error_type=error_type,
                message=message,
                endpoint=endpoint,
                status_code=status_code,
                symbol=symbol,
            )
        ],
    )


class FmpTranscriptAdapter:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://financialmodelingprep.com/api/v3",
        timeout_seconds: float = 10.0,
        http_client: SyncHttpClient | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client or _DefaultHttpClient()

    def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
        fetched_at: datetime | None = None,
    ) -> TranscriptResult:
        symbol = ticker.strip().upper()
        endpoint = f"/earning_call_transcript/{symbol}"
        if not self._api_key:
            return _transcript_error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP API key is required for earnings-call transcript.",
            )

        try:
            response = self._http_client.get(
                f"{self._base_url}{endpoint}",
                params={"quarter": str(quarter), "year": str(year), "apikey": self._api_key},
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException):
            return _transcript_error_result(
                DataProviderErrorType.TIMEOUT,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP earnings-call transcript request timed out.",
            )
        except httpx.HTTPError:
            return _transcript_error_result(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP earnings-call transcript provider is unavailable.",
            )

        status_error = _status_error(response.status_code)
        if status_error is not None:
            return _transcript_error_result(
                status_error,
                endpoint=endpoint,
                symbol=symbol,
                status_code=response.status_code,
                message="FMP earnings-call transcript request failed.",
            )

        try:
            payload = response.json()
        except (TypeError, ValueError):
            return _transcript_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP earnings-call transcript response was not valid JSON.",
            )

        if not isinstance(payload, list):
            if isinstance(payload, dict) and "Error Message" in payload:
                return _transcript_error_result(
                    DataProviderErrorType.UNAUTHORIZED,
                    endpoint=endpoint,
                    symbol=symbol,
                    message=payload["Error Message"],
                )
            return _transcript_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP earnings-call transcript response was not a list.",
            )

        if not payload:
            return _transcript_error_result(
                DataProviderErrorType.TRANSCRIPT_NOT_FOUND,
                endpoint=endpoint,
                symbol=symbol,
                message=f"FMP transcript not found for {symbol} Q{quarter} {year}.",
            )

        matching_entry = None
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            entry_quarter = entry.get("quarter")
            entry_year = entry.get("year")
            try:
                if int(entry_quarter) == quarter and int(entry_year) == year:
                    matching_entry = entry
                    break
            except (ValueError, TypeError):
                continue

        if matching_entry is None:
            if len(payload) == 1:
                matching_entry = payload[0]
            else:
                return _transcript_error_result(
                    DataProviderErrorType.TRANSCRIPT_NOT_FOUND,
                    endpoint=endpoint,
                    symbol=symbol,
                    message=f"FMP transcript not found for {symbol} Q{quarter} {year}.",
                )

        content = matching_entry.get("content")
        if not content or not isinstance(content, str):
            return _transcript_error_result(
                DataProviderErrorType.EMPTY_RESPONSE,
                endpoint=endpoint,
                symbol=symbol,
                message="FMP transcript content was empty or missing.",
            )

        snapshot = TranscriptSnapshot(
            ticker=symbol,
            quarter=quarter,
            year=year,
            content=content,
            provider=DataProvider.FMP,
            source_endpoint=endpoint,
            fetched_at=fetched_at,
        )
        return TranscriptResult(snapshots=[snapshot], errors=[])


def _transcript_error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> TranscriptResult:
    return TranscriptResult(
        snapshots=[],
        errors=[
            DataProviderError(
                provider=DataProvider.FMP,
                error_type=error_type,
                message=message,
                endpoint=endpoint,
                status_code=status_code,
                symbol=symbol,
            )
        ],
    )
