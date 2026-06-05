from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Protocol, TypeVar, cast

import httpx

from prescient.data.models import (
    CompanyEarningsResult,
    CompanyEarningsSnapshot,
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    EarningsCalendarResult,
    EarningsCalendarSnapshot,
    EarningsEstimateResult,
    EarningsEstimateSnapshot,
    RevenueEstimateResult,
    RevenueEstimateSnapshot,
)


_EARNINGS_CALENDAR_ENDPOINT = "/calendar/earnings"
_COMPANY_EARNINGS_ENDPOINT = "/stock/earnings"
_EPS_ESTIMATE_ENDPOINT = "/stock/eps-estimate"
_REVENUE_ESTIMATE_ENDPOINT = "/stock/revenue-estimate"

_ResultT = TypeVar(
    "_ResultT",
    EarningsCalendarResult,
    CompanyEarningsResult,
    EarningsEstimateResult,
    RevenueEstimateResult,
)


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


class FinnhubEarningsAdapter:
    def __init__(
        self,
        *,
        token: str | None,
        base_url: str = "https://finnhub.io/api/v1",
        timeout_seconds: float = 10.0,
        http_client: SyncHttpClient | None = None,
        prefer_broad_calendar: bool = False,
    ) -> None:
        self.token = token.strip() if token is not None else ""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or _DefaultHttpClient()
        # Finnhub's free tier returns empty for per-symbol calendar queries; broad
        # mode fetches the whole calendar once and filters to requested tickers.
        self.prefer_broad_calendar = prefer_broad_calendar

    def get_earnings_calendar(
        self,
        date_from: date,
        date_to: date,
        tickers: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> EarningsCalendarResult:
        symbols = _normalize_symbols(tickers or [])
        if not self.token:
            return _calendar_error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=_EARNINGS_CALENDAR_ENDPOINT,
                symbol=",".join(symbols) or None,
                message="Finnhub token is required for earnings calendar.",
            )

        base_params: dict[str, Any] = {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
        }
        if not symbols:
            response = self._get(
                _EARNINGS_CALENDAR_ENDPOINT,
                params={**base_params, "token": self.token},
                symbol=None,
            )
            if isinstance(response, DataProviderError):
                return EarningsCalendarResult(errors=[response])
            return _parse_calendar_response(
                response,
                requested_symbol=None,
                fetched_at=fetched_at,
            )

        if self.prefer_broad_calendar:
            # Free-tier-safe: one broad call, filter to requested tickers locally.
            response = self._get(
                _EARNINGS_CALENDAR_ENDPOINT,
                params={**base_params, "token": self.token},
                symbol=None,
            )
            if isinstance(response, DataProviderError):
                return EarningsCalendarResult(errors=[response])
            result = _parse_calendar_response(
                response,
                requested_symbol=None,
                fetched_at=fetched_at,
            )
            wanted = set(symbols)
            filtered = [s for s in result.snapshots if s.ticker in wanted]
            return EarningsCalendarResult(snapshots=filtered, errors=result.errors)

        snapshots: list[EarningsCalendarSnapshot] = []
        errors: list[DataProviderError] = []
        for symbol in symbols:
            response = self._get(
                _EARNINGS_CALENDAR_ENDPOINT,
                params={**base_params, "symbol": symbol, "token": self.token},
                symbol=symbol,
            )
            if isinstance(response, DataProviderError):
                errors.append(response)
                continue

            result = _parse_calendar_response(
                response,
                requested_symbol=symbol,
                fetched_at=fetched_at,
            )
            snapshots.extend(result.snapshots)
            errors.extend(result.errors)

        return EarningsCalendarResult(snapshots=snapshots, errors=errors)

    def get_company_earnings(
        self,
        ticker: str,
        limit: int | None = None,
        fetched_at: datetime | None = None,
    ) -> CompanyEarningsResult:
        symbol = _normalize_symbol(ticker)
        if not self.token:
            return _company_error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=_COMPANY_EARNINGS_ENDPOINT,
                symbol=symbol,
                message="Finnhub token is required for company earnings.",
            )

        params: dict[str, Any] = {"symbol": symbol, "token": self.token}
        if limit is not None:
            params["limit"] = limit

        response = self._get(_COMPANY_EARNINGS_ENDPOINT, params=params, symbol=symbol)
        if isinstance(response, DataProviderError):
            return CompanyEarningsResult(errors=[response])

        return _parse_company_earnings_response(
            response,
            requested_symbol=symbol,
            fetched_at=fetched_at,
        )

    def get_eps_estimates(
        self,
        ticker: str,
        freq: str = "quarterly",
        fetched_at: datetime | None = None,
    ) -> EarningsEstimateResult:
        symbol = _normalize_symbol(ticker)
        normalized_freq = freq.strip().lower()
        if not self.token:
            return _eps_error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=_EPS_ESTIMATE_ENDPOINT,
                symbol=symbol,
                message="Finnhub token is required for EPS estimates.",
            )

        response = self._get(
            _EPS_ESTIMATE_ENDPOINT,
            params={"symbol": symbol, "freq": normalized_freq, "token": self.token},
            symbol=symbol,
        )
        if isinstance(response, DataProviderError):
            return EarningsEstimateResult(errors=[response])

        return _parse_eps_estimate_response(
            response,
            requested_symbol=symbol,
            requested_freq=normalized_freq,
            fetched_at=fetched_at,
        )

    def get_revenue_estimates(
        self,
        ticker: str,
        freq: str = "quarterly",
        fetched_at: datetime | None = None,
    ) -> RevenueEstimateResult:
        symbol = _normalize_symbol(ticker)
        normalized_freq = freq.strip().lower()
        if not self.token:
            return _revenue_error_result(
                DataProviderErrorType.MISSING_API_KEY,
                endpoint=_REVENUE_ESTIMATE_ENDPOINT,
                symbol=symbol,
                message="Finnhub token is required for revenue estimates.",
            )

        response = self._get(
            _REVENUE_ESTIMATE_ENDPOINT,
            params={"symbol": symbol, "freq": normalized_freq, "token": self.token},
            symbol=symbol,
        )
        if isinstance(response, DataProviderError):
            return RevenueEstimateResult(errors=[response])

        return _parse_revenue_estimate_response(
            response,
            requested_symbol=symbol,
            requested_freq=normalized_freq,
            fetched_at=fetched_at,
        )

    def _get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
        symbol: str | None,
    ) -> SyncHttpResponse | DataProviderError:
        try:
            response = self.http_client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=self.timeout_seconds,
            )
        except (TimeoutError, httpx.TimeoutException):
            return _provider_error(
                DataProviderErrorType.TIMEOUT,
                endpoint=endpoint,
                symbol=symbol,
                message=_timeout_message(endpoint),
            )
        except httpx.HTTPError:
            return _provider_error(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                endpoint=endpoint,
                symbol=symbol,
                message=_unavailable_message(endpoint),
            )

        status_error = _status_error(response.status_code)
        if status_error is not None:
            return _provider_error(
                status_error,
                endpoint=endpoint,
                symbol=symbol,
                status_code=response.status_code,
                message=_message_for_status_error(endpoint, status_error),
            )

        return response


def to_upcoming_calendar_events(
    result: EarningsCalendarResult,
) -> list[Any]:
    from prescient.signal.models import EarningsCalendarEvent

    events: list[EarningsCalendarEvent] = []
    for snapshot in result.snapshots:
        if snapshot.eps_actual is not None or snapshot.revenue_actual is not None:
            continue
        events.append(
            EarningsCalendarEvent(
                ticker=snapshot.ticker,
                earnings_date=snapshot.earnings_date,
                report_time=cast(Any, snapshot.report_time),
                eps_estimate=snapshot.eps_estimate,
                revenue_estimate=snapshot.revenue_estimate,
            )
        )
    return events


def to_completed_peer_events(result: EarningsCalendarResult) -> list[Any]:
    from prescient.signal.models import EarningsEvent

    events: list[EarningsEvent] = []
    for snapshot in result.snapshots:
        if snapshot.earnings_date is None:
            continue
        if snapshot.eps_actual is None and snapshot.revenue_actual is None:
            continue
        events.append(
            EarningsEvent(
                ticker=snapshot.ticker,
                earnings_date=snapshot.earnings_date,
                report_time=cast(Any, snapshot.report_time),
                eps_estimate=snapshot.eps_estimate,
                eps_actual=snapshot.eps_actual,
                revenue_estimate=snapshot.revenue_estimate,
                revenue_actual=snapshot.revenue_actual,
            )
        )
    return events


def _parse_calendar_response(
    response: SyncHttpResponse,
    *,
    requested_symbol: str | None,
    fetched_at: datetime | None,
) -> EarningsCalendarResult:
    payload = _response_payload(
        response,
        result_type=EarningsCalendarResult,
        endpoint=_EARNINGS_CALENDAR_ENDPOINT,
        symbol=requested_symbol,
    )
    if isinstance(payload, EarningsCalendarResult):
        return payload

    entries = _extract_entries(payload, keys=("earningsCalendar",))
    if entries is None:
        return _calendar_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_EARNINGS_CALENDAR_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub earnings calendar response had an unsupported shape.",
        )
    if not entries:
        return _calendar_error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            endpoint=_EARNINGS_CALENDAR_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub earnings calendar response was empty.",
        )

    snapshots: list[EarningsCalendarSnapshot] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return _calendar_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=_EARNINGS_CALENDAR_ENDPOINT,
                symbol=requested_symbol,
                message="Finnhub earnings calendar entry had an unsupported shape.",
            )
        snapshot = _calendar_snapshot_from_entry(
            entry,
            requested_symbol=requested_symbol,
            fetched_at=fetched_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    if not snapshots:
        return _calendar_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_EARNINGS_CALENDAR_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub earnings calendar response did not include valid symbols.",
        )
    return EarningsCalendarResult(snapshots=snapshots)


def _parse_company_earnings_response(
    response: SyncHttpResponse,
    *,
    requested_symbol: str,
    fetched_at: datetime | None,
) -> CompanyEarningsResult:
    payload = _response_payload(
        response,
        result_type=CompanyEarningsResult,
        endpoint=_COMPANY_EARNINGS_ENDPOINT,
        symbol=requested_symbol,
    )
    if isinstance(payload, CompanyEarningsResult):
        return payload

    entries = _extract_entries(payload, keys=("earnings", "data"))
    if entries is None:
        return _company_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_COMPANY_EARNINGS_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub company earnings response had an unsupported shape.",
        )
    if not entries:
        return _company_error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            endpoint=_COMPANY_EARNINGS_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub company earnings response was empty.",
        )

    snapshots: list[CompanyEarningsSnapshot] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return _company_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=_COMPANY_EARNINGS_ENDPOINT,
                symbol=requested_symbol,
                message="Finnhub company earnings entry had an unsupported shape.",
            )
        snapshot = _company_earnings_snapshot_from_entry(
            entry,
            requested_symbol=requested_symbol,
            fetched_at=fetched_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    if not snapshots:
        return _company_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_COMPANY_EARNINGS_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub company earnings response did not include valid symbols.",
        )
    return CompanyEarningsResult(snapshots=snapshots)


def _parse_eps_estimate_response(
    response: SyncHttpResponse,
    *,
    requested_symbol: str,
    requested_freq: str,
    fetched_at: datetime | None,
) -> EarningsEstimateResult:
    payload = _response_payload(
        response,
        result_type=EarningsEstimateResult,
        endpoint=_EPS_ESTIMATE_ENDPOINT,
        symbol=requested_symbol,
    )
    if isinstance(payload, EarningsEstimateResult):
        return payload

    entries = _extract_entries(payload, keys=("data",))
    if entries is None:
        return _eps_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_EPS_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub EPS estimate response had an unsupported shape.",
        )
    if not entries:
        return _eps_error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            endpoint=_EPS_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub EPS estimate response was empty.",
        )

    snapshots: list[EarningsEstimateSnapshot] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return _eps_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=_EPS_ESTIMATE_ENDPOINT,
                symbol=requested_symbol,
                message="Finnhub EPS estimate entry had an unsupported shape.",
            )
        snapshot = _eps_estimate_snapshot_from_entry(
            entry,
            requested_symbol=requested_symbol,
            requested_freq=requested_freq,
            fetched_at=fetched_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    if not snapshots:
        return _eps_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_EPS_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub EPS estimate response did not include valid symbols.",
        )
    return EarningsEstimateResult(snapshots=snapshots)


def _parse_revenue_estimate_response(
    response: SyncHttpResponse,
    *,
    requested_symbol: str,
    requested_freq: str,
    fetched_at: datetime | None,
) -> RevenueEstimateResult:
    payload = _response_payload(
        response,
        result_type=RevenueEstimateResult,
        endpoint=_REVENUE_ESTIMATE_ENDPOINT,
        symbol=requested_symbol,
    )
    if isinstance(payload, RevenueEstimateResult):
        return payload

    entries = _extract_entries(payload, keys=("data",))
    if entries is None:
        return _revenue_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_REVENUE_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub revenue estimate response had an unsupported shape.",
        )
    if not entries:
        return _revenue_error_result(
            DataProviderErrorType.EMPTY_RESPONSE,
            endpoint=_REVENUE_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub revenue estimate response was empty.",
        )

    snapshots: list[RevenueEstimateSnapshot] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return _revenue_error_result(
                DataProviderErrorType.MALFORMED_RESPONSE,
                endpoint=_REVENUE_ESTIMATE_ENDPOINT,
                symbol=requested_symbol,
                message="Finnhub revenue estimate entry had an unsupported shape.",
            )
        snapshot = _revenue_estimate_snapshot_from_entry(
            entry,
            requested_symbol=requested_symbol,
            requested_freq=requested_freq,
            fetched_at=fetched_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)

    if not snapshots:
        return _revenue_error_result(
            DataProviderErrorType.MALFORMED_RESPONSE,
            endpoint=_REVENUE_ESTIMATE_ENDPOINT,
            symbol=requested_symbol,
            message="Finnhub revenue estimate response did not include valid symbols.",
        )
    return RevenueEstimateResult(snapshots=snapshots)


def _calendar_snapshot_from_entry(
    entry: Mapping[str, Any],
    *,
    requested_symbol: str | None,
    fetched_at: datetime | None,
) -> EarningsCalendarSnapshot | None:
    symbol = _symbol_from_entry(entry, requested_symbol=requested_symbol)
    if symbol is None:
        return None

    return EarningsCalendarSnapshot(
        ticker=symbol,
        earnings_date=_date_or_none(entry.get("date")),
        report_time=_report_time(entry.get("hour")),
        fiscal_year=_int_or_none(entry.get("year")),
        fiscal_quarter=_int_or_none(entry.get("quarter")),
        eps_estimate=_float_or_none(entry.get("epsEstimate")),
        eps_actual=_float_or_none(entry.get("epsActual")),
        revenue_estimate=_float_or_none(entry.get("revenueEstimate")),
        revenue_actual=_float_or_none(entry.get("revenueActual")),
        provider=DataProvider.FINNHUB,
        source_endpoint=_EARNINGS_CALENDAR_ENDPOINT,
        provider_notes=[],
        fetched_at=fetched_at,
    )


def _company_earnings_snapshot_from_entry(
    entry: Mapping[str, Any],
    *,
    requested_symbol: str,
    fetched_at: datetime | None,
) -> CompanyEarningsSnapshot | None:
    symbol = _symbol_from_entry(entry, requested_symbol=requested_symbol)
    if symbol is None:
        return None

    return CompanyEarningsSnapshot(
        ticker=symbol,
        fiscal_period=_string_or_none(entry.get("period")),
        fiscal_year=_int_or_none(entry.get("year")),
        fiscal_quarter=_int_or_none(entry.get("quarter")),
        eps_actual=_float_or_none(entry.get("actual")),
        eps_estimate=_float_or_none(entry.get("estimate")),
        eps_surprise=_float_or_none(entry.get("surprise")),
        eps_surprise_percent=_float_or_none(entry.get("surprisePercent")),
        provider=DataProvider.FINNHUB,
        source_endpoint=_COMPANY_EARNINGS_ENDPOINT,
        provider_notes=[],
        fetched_at=fetched_at,
    )


def _eps_estimate_snapshot_from_entry(
    entry: Mapping[str, Any],
    *,
    requested_symbol: str,
    requested_freq: str,
    fetched_at: datetime | None,
) -> EarningsEstimateSnapshot | None:
    symbol = _symbol_from_entry(entry, requested_symbol=requested_symbol)
    if symbol is None:
        return None

    return EarningsEstimateSnapshot(
        ticker=symbol,
        fiscal_period=_string_or_none(entry.get("period")),
        freq=_string_or_none(entry.get("freq")) or requested_freq,
        fiscal_year=_int_or_none(entry.get("year")),
        fiscal_quarter=_int_or_none(entry.get("quarter")),
        eps_average=_float_from_keys(entry, ("epsAvg", "epsAverage")),
        eps_high=_float_from_keys(entry, ("epsHigh",)),
        eps_low=_float_from_keys(entry, ("epsLow",)),
        analyst_count=_int_from_keys(entry, ("numberAnalysts", "numberAnalyst", "analystCount")),
        provider=DataProvider.FINNHUB,
        source_endpoint=_EPS_ESTIMATE_ENDPOINT,
        provider_notes=[],
        fetched_at=fetched_at,
    )


def _revenue_estimate_snapshot_from_entry(
    entry: Mapping[str, Any],
    *,
    requested_symbol: str,
    requested_freq: str,
    fetched_at: datetime | None,
) -> RevenueEstimateSnapshot | None:
    symbol = _symbol_from_entry(entry, requested_symbol=requested_symbol)
    if symbol is None:
        return None

    return RevenueEstimateSnapshot(
        ticker=symbol,
        fiscal_period=_string_or_none(entry.get("period")),
        freq=_string_or_none(entry.get("freq")) or requested_freq,
        fiscal_year=_int_or_none(entry.get("year")),
        fiscal_quarter=_int_or_none(entry.get("quarter")),
        revenue_average=_float_from_keys(entry, ("revenueAvg", "revenueAverage")),
        revenue_high=_float_from_keys(entry, ("revenueHigh",)),
        revenue_low=_float_from_keys(entry, ("revenueLow",)),
        analyst_count=_int_from_keys(entry, ("numberAnalysts", "numberAnalyst", "analystCount")),
        provider=DataProvider.FINNHUB,
        source_endpoint=_REVENUE_ESTIMATE_ENDPOINT,
        provider_notes=[],
        fetched_at=fetched_at,
    )


def _response_payload(
    response: SyncHttpResponse,
    *,
    result_type: type[_ResultT],
    endpoint: str,
    symbol: str | None,
) -> Any | _ResultT:
    try:
        return response.json()
    except (TypeError, ValueError):
        return result_type(
            errors=[
                _provider_error(
                    DataProviderErrorType.MALFORMED_RESPONSE,
                    endpoint=endpoint,
                    symbol=symbol,
                    message=f"Finnhub {_endpoint_label(endpoint)} response was not valid JSON.",
                )
            ]
        )


def _extract_entries(payload: Any, *, keys: Sequence[str]) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _symbol_from_entry(
    entry: Mapping[str, Any],
    *,
    requested_symbol: str | None,
) -> str | None:
    raw_symbol = entry.get("symbol", requested_symbol)
    if not isinstance(raw_symbol, str):
        return None
    symbol = _normalize_symbol(raw_symbol)
    return symbol or None


def _normalize_symbols(values: Sequence[str]) -> list[str]:
    symbols: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        symbol = _normalize_symbol(value)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _normalize_symbol(value: str) -> str:
    return value.strip().upper()


def _report_time(value: Any) -> str:
    text = _string_or_none(value)
    if text is None:
        return "UNKNOWN"

    lowered = text.lower().replace("-", " ").replace("_", " ")
    if lowered in {
        "bmo",
        "before market open",
        "before open",
        "before market",
        "pre market",
        "premarket",
    }:
        return "BMO"
    if lowered in {
        "amc",
        "after market close",
        "after close",
        "after market",
        "post market",
        "postmarket",
    }:
        return "AMC"
    return "UNKNOWN"


def _date_or_none(value: Any) -> date | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _float_from_keys(entry: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _float_or_none(entry.get(key))
        if value is not None:
            return value
    return None


def _int_from_keys(entry: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        value = _int_or_none(entry.get(key))
        if value is not None:
            return value
    return None


def _status_error(status_code: int) -> DataProviderErrorType | None:
    if status_code in {401, 403}:
        return DataProviderErrorType.UNAUTHORIZED
    if status_code == 402:
        return DataProviderErrorType.PAYMENT_REQUIRED
    if status_code == 404:
        return DataProviderErrorType.UNSUPPORTED_SYMBOL
    if status_code == 429:
        return DataProviderErrorType.RATE_LIMITED
    if status_code >= 500:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    if status_code >= 400:
        return DataProviderErrorType.PROVIDER_UNAVAILABLE
    return None


def _message_for_status_error(endpoint: str, error_type: DataProviderErrorType) -> str:
    label = _endpoint_label(endpoint)
    messages = {
        DataProviderErrorType.UNAUTHORIZED: f"Finnhub {label} access is unauthorized.",
        DataProviderErrorType.PAYMENT_REQUIRED: f"Finnhub {label} access requires payment.",
        DataProviderErrorType.RATE_LIMITED: f"Finnhub {label} request was rate limited.",
        DataProviderErrorType.UNSUPPORTED_SYMBOL: f"Finnhub {label} symbol is unsupported.",
        DataProviderErrorType.PROVIDER_UNAVAILABLE: f"Finnhub {label} provider is unavailable.",
    }
    return messages.get(error_type, f"Finnhub {label} request failed.")


def _timeout_message(endpoint: str) -> str:
    return f"Finnhub {_endpoint_label(endpoint)} request timed out."


def _unavailable_message(endpoint: str) -> str:
    return f"Finnhub {_endpoint_label(endpoint)} provider is unavailable."


def _endpoint_label(endpoint: str) -> str:
    labels = {
        _EARNINGS_CALENDAR_ENDPOINT: "earnings calendar",
        _COMPANY_EARNINGS_ENDPOINT: "company earnings",
        _EPS_ESTIMATE_ENDPOINT: "EPS estimate",
        _REVENUE_ESTIMATE_ENDPOINT: "revenue estimate",
    }
    return labels.get(endpoint, "earnings")


def _calendar_error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> EarningsCalendarResult:
    return EarningsCalendarResult(
        errors=[
            _provider_error(
                error_type,
                endpoint=endpoint,
                symbol=symbol,
                message=message,
                status_code=status_code,
            )
        ]
    )


def _company_error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> CompanyEarningsResult:
    return CompanyEarningsResult(
        errors=[
            _provider_error(
                error_type,
                endpoint=endpoint,
                symbol=symbol,
                message=message,
                status_code=status_code,
            )
        ]
    )


def _eps_error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> EarningsEstimateResult:
    return EarningsEstimateResult(
        errors=[
            _provider_error(
                error_type,
                endpoint=endpoint,
                symbol=symbol,
                message=message,
                status_code=status_code,
            )
        ]
    )


def _revenue_error_result(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> RevenueEstimateResult:
    return RevenueEstimateResult(
        errors=[
            _provider_error(
                error_type,
                endpoint=endpoint,
                symbol=symbol,
                message=message,
                status_code=status_code,
            )
        ]
    )


def _provider_error(
    error_type: DataProviderErrorType,
    *,
    endpoint: str,
    symbol: str | None,
    message: str,
    status_code: int | None = None,
) -> DataProviderError:
    return DataProviderError(
        provider=DataProvider.FINNHUB,
        error_type=error_type,
        message=message,
        endpoint=endpoint,
        status_code=status_code,
        symbol=symbol,
    )
