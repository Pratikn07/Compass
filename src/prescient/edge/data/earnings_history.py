from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol, Sequence

import httpx

from prescient.data.models import DataProvider, DataProviderError, DataProviderErrorType
from prescient.edge.data.models import EarningsAnnouncement

_EARNINGS_FUNCTION = "EARNINGS"
_QUERY_PATH = "/query"
_REPORT_TIME_MAP = {
    "pre-market": "BMO",
    "post-market": "AMC",
    "bmo": "BMO",
    "amc": "AMC",
}


class SyncHttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class SyncHttpClient(Protocol):
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> SyncHttpResponse: ...


class _DefaultHttpClient:
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> SyncHttpResponse:
        return httpx.get(url, params=params, timeout=timeout)


class EarningsHistoryProvider(Protocol):
    def get_earnings_history(
        self, *, tickers: Sequence[str], start: date, end: date
    ) -> tuple[list[EarningsAnnouncement], list[DataProviderError]]: ...


def _err(error_type: DataProviderErrorType, message: str, symbol: str | None = None,
         status_code: int | None = None) -> DataProviderError:
    return DataProviderError(
        provider=DataProvider.ALPHA_VANTAGE,
        error_type=error_type,
        message=message,
        endpoint=_QUERY_PATH,
        status_code=status_code,
        symbol=symbol,
    )


def _to_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


class AlphaVantageEarningsHistoryAdapter:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://www.alphavantage.co",
        timeout_seconds: float = 15.0,
        http_client: SyncHttpClient | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client or _DefaultHttpClient()

    def get_earnings_history(
        self, *, tickers: Sequence[str], start: date, end: date
    ) -> tuple[list[EarningsAnnouncement], list[DataProviderError]]:
        announcements: list[EarningsAnnouncement] = []
        errors: list[DataProviderError] = []
        if not self._api_key:
            errors.append(_err(DataProviderErrorType.MISSING_API_KEY,
                               "Alpha Vantage API key is required for earnings history."))
            return announcements, errors

        seen: set[str] = set()
        for raw in tickers:
            symbol = raw.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            payload = self._fetch(symbol, errors)
            if payload is None:
                continue
            quarterly = payload.get("quarterlyEarnings")
            if not isinstance(quarterly, list):
                errors.append(_err(DataProviderErrorType.RATE_LIMITED,
                                   "Alpha Vantage returned no earnings data "
                                   "(rate limit or empty).", symbol=symbol))
                continue
            for row in quarterly:
                if not isinstance(row, dict):
                    continue
                report_date = _parse_date(row.get("reportedDate"))
                if report_date is None or not (start <= report_date <= end):
                    continue
                announcements.append(
                    EarningsAnnouncement(
                        ticker=symbol,
                        report_date=report_date,
                        report_time=_REPORT_TIME_MAP.get(
                            str(row.get("reportTime", "")).strip().lower(), "UNKNOWN"
                        ),
                        eps_estimate=_to_float(row.get("estimatedEPS")),
                        eps_actual=_to_float(row.get("reportedEPS")),
                        surprise_pct=_to_float(row.get("surprisePercentage")),
                    )
                )
        return announcements, errors

    def _fetch(self, symbol: str, errors: list[DataProviderError]) -> dict[str, Any] | None:
        params = {"function": _EARNINGS_FUNCTION, "symbol": symbol, "apikey": self._api_key}
        try:
            response = self._http_client.get(
                f"{self._base_url}{_QUERY_PATH}", params=params, timeout=self._timeout_seconds
            )
        except (TimeoutError, httpx.TimeoutException):
            errors.append(_err(DataProviderErrorType.TIMEOUT,
                               "Alpha Vantage earnings request timed out.", symbol=symbol))
            return None
        except httpx.HTTPError:
            errors.append(_err(DataProviderErrorType.PROVIDER_UNAVAILABLE,
                               "Alpha Vantage earnings provider is unavailable.", symbol=symbol))
            return None
        if response.status_code != 200:
            errors.append(_err(DataProviderErrorType.PROVIDER_UNAVAILABLE,
                               "Alpha Vantage earnings returned a non-200 status.",
                               symbol=symbol, status_code=response.status_code))
            return None
        try:
            payload = response.json()
        except ValueError:
            errors.append(_err(DataProviderErrorType.MALFORMED_RESPONSE,
                               "Alpha Vantage earnings returned malformed JSON.", symbol=symbol))
            return None
        if not isinstance(payload, dict):
            errors.append(_err(DataProviderErrorType.MALFORMED_RESPONSE,
                               "Alpha Vantage earnings payload was not an object.", symbol=symbol))
            return None
        return payload
