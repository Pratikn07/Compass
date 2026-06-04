from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


R4_1_PRD_PATH = Path(
    "docs/prd/04-data-r4-1-earnings-calendar-estimates-actuals-finnhub-prd.md"
)


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(
        self,
        response: FakeHttpResponse | Exception | list[FakeHttpResponse | Exception],
    ) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def test_r4_1_prd_is_saved_for_finnhub_earnings_calendar_estimates_and_actuals() -> None:
    prd = R4_1_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R4.1 Finnhub Earnings Calendar + Estimates / Actuals" in prd
    assert "Finnhub" in prd
    assert "Earnings Calendar" in prd
    assert "Company Earnings" in prd
    assert "Company EPS Estimates" in prd
    assert "Company Revenue Estimates" in prd
    assert "No continuous polling loop" in prd


def test_calendar_response_normalizes_snapshot_and_uses_symbol_bounded_request() -> None:
    from prescient.data import DataProvider, FinnhubEarningsAdapter

    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "earningsCalendar": [
                    {
                        "symbol": "ntnx",
                        "date": "2026-06-02",
                        "hour": "bmo",
                        "year": "2026",
                        "quarter": "2",
                        "epsEstimate": "1.23",
                        "epsActual": "1.45",
                        "revenueEstimate": "1234567890",
                        "revenueActual": "1333000000",
                    }
                ]
            }
        )
    )
    fetched_at = datetime(2026, 6, 3, 17, 30, tzinfo=timezone.utc)
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)

    result = adapter.get_earnings_calendar(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 3),
        tickers=["ntnx"],
        fetched_at=fetched_at,
    )

    assert result.errors == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.ticker == "NTNX"
    assert snapshot.earnings_date == date(2026, 6, 2)
    assert snapshot.report_time == "BMO"
    assert snapshot.fiscal_year == 2026
    assert snapshot.fiscal_quarter == 2
    assert snapshot.eps_estimate == 1.23
    assert snapshot.eps_actual == 1.45
    assert snapshot.revenue_estimate == 1_234_567_890.0
    assert snapshot.revenue_actual == 1_333_000_000.0
    assert snapshot.provider == DataProvider.FINNHUB
    assert snapshot.source_endpoint == "/calendar/earnings"
    assert snapshot.fetched_at == fetched_at
    assert client.calls == [
        {
            "url": "https://finnhub.io/api/v1/calendar/earnings",
            "params": {
                "from": "2026-06-01",
                "to": "2026-06-03",
                "symbol": "NTNX",
                "token": "secret-token",
            },
            "timeout": 10.0,
        }
    ]


def test_calendar_lookup_deduplicates_tickers_and_preserves_request_order() -> None:
    from prescient.data import FinnhubEarningsAdapter

    client = FakeHttpClient(
        [
            FakeHttpResponse(
                payload={"earningsCalendar": [{"symbol": "aapl", "date": "2026-06-01"}]}
            ),
            FakeHttpResponse(
                payload={"earningsCalendar": [{"symbol": "msft", "date": "2026-06-02"}]}
            ),
        ]
    )
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)

    result = adapter.get_earnings_calendar(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 3),
        tickers=["aapl", "MSFT", "aapl", " "],
    )

    assert result.errors == []
    assert [snapshot.ticker for snapshot in result.snapshots] == ["AAPL", "MSFT"]
    assert [call["params"]["symbol"] for call in client.calls] == ["AAPL", "MSFT"]


def test_calendar_snapshots_convert_to_upcoming_events_when_actuals_are_missing() -> None:
    from prescient.data import FinnhubEarningsAdapter, to_upcoming_calendar_events

    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "earningsCalendar": [
                    {
                        "symbol": "ntnx",
                        "date": "2026-06-02",
                        "hour": "amc",
                        "epsEstimate": "1.10",
                        "revenueEstimate": "1000",
                    },
                    {
                        "symbol": "ntap",
                        "date": "2026-06-03",
                        "epsEstimate": "1.20",
                        "epsActual": "1.30",
                    },
                ]
            }
        )
    )
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)
    result = adapter.get_earnings_calendar(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 3),
    )

    events = to_upcoming_calendar_events(result)

    assert len(events) == 1
    assert events[0].ticker == "NTNX"
    assert events[0].earnings_date == date(2026, 6, 2)
    assert events[0].report_time == "AMC"
    assert events[0].eps_estimate == 1.10
    assert events[0].revenue_estimate == 1000.0


def test_calendar_snapshots_convert_to_completed_events_when_actuals_are_present() -> None:
    from prescient.data import FinnhubEarningsAdapter, to_completed_peer_events

    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "earningsCalendar": [
                    {
                        "symbol": "ntap",
                        "date": "2026-05-20",
                        "hour": "amc",
                        "epsEstimate": "1.10",
                        "epsActual": "1.30",
                        "revenueEstimate": "1000",
                        "revenueActual": "1200",
                    },
                    {
                        "symbol": "pstg",
                        "date": "not-a-date",
                        "epsActual": "1.20",
                    },
                    {
                        "symbol": "wdc",
                        "date": "2026-05-22",
                        "epsEstimate": "1.00",
                    },
                ]
            }
        )
    )
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)
    result = adapter.get_earnings_calendar(
        date_from=date(2026, 5, 20),
        date_to=date(2026, 5, 23),
    )

    events = to_completed_peer_events(result)

    assert len(events) == 1
    assert events[0].ticker == "NTAP"
    assert events[0].earnings_date == date(2026, 5, 20)
    assert events[0].report_time == "AMC"
    assert events[0].eps_estimate == 1.10
    assert events[0].eps_actual == 1.30
    assert events[0].revenue_estimate == 1000.0
    assert events[0].revenue_actual == 1200.0


def test_company_earnings_response_normalizes_eps_history_without_report_date_fabrication() -> None:
    from prescient.data import DataProvider, FinnhubEarningsAdapter

    client = FakeHttpClient(
        FakeHttpResponse(
            payload=[
                {
                    "symbol": "ntnx",
                    "period": "2026-03-31",
                    "year": "2026",
                    "quarter": "1",
                    "actual": "1.45",
                    "estimate": "1.23",
                    "surprise": "0.22",
                    "surprisePercent": "17.89",
                }
            ]
        )
    )
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)

    result = adapter.get_company_earnings("ntnx", limit=4)

    assert result.errors == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.ticker == "NTNX"
    assert snapshot.fiscal_period == "2026-03-31"
    assert snapshot.fiscal_year == 2026
    assert snapshot.fiscal_quarter == 1
    assert snapshot.eps_actual == 1.45
    assert snapshot.eps_estimate == 1.23
    assert snapshot.eps_surprise == 0.22
    assert snapshot.eps_surprise_percent == 17.89
    assert snapshot.provider == DataProvider.FINNHUB
    assert snapshot.source_endpoint == "/stock/earnings"
    assert client.calls[0]["params"] == {
        "symbol": "NTNX",
        "limit": 4,
        "token": "secret-token",
    }


def test_eps_and_revenue_estimate_responses_normalize_quarterly_snapshots() -> None:
    from prescient.data import FinnhubEarningsAdapter

    client = FakeHttpClient(
        [
            FakeHttpResponse(
                payload={
                    "data": [
                        {
                            "symbol": "ntnx",
                            "period": "2026-06-30",
                            "freq": "quarterly",
                            "year": "2026",
                            "quarter": "2",
                            "epsAvg": "1.23",
                            "epsHigh": "1.30",
                            "epsLow": "1.10",
                            "numberAnalysts": "12",
                        }
                    ]
                }
            ),
            FakeHttpResponse(
                payload={
                    "data": [
                        {
                            "symbol": "ntnx",
                            "period": "2026-06-30",
                            "freq": "quarterly",
                            "year": "2026",
                            "quarter": "2",
                            "revenueAvg": "1234567890",
                            "revenueHigh": "1300000000",
                            "revenueLow": "1200000000",
                            "numberAnalysts": "10",
                        }
                    ]
                }
            ),
        ]
    )
    adapter = FinnhubEarningsAdapter(token="secret-token", http_client=client)

    eps_result = adapter.get_eps_estimates("ntnx", freq="quarterly")
    revenue_result = adapter.get_revenue_estimates("ntnx", freq="quarterly")

    assert eps_result.errors == []
    assert eps_result.snapshots[0].ticker == "NTNX"
    assert eps_result.snapshots[0].fiscal_period == "2026-06-30"
    assert eps_result.snapshots[0].freq == "quarterly"
    assert eps_result.snapshots[0].eps_average == 1.23
    assert eps_result.snapshots[0].eps_high == 1.30
    assert eps_result.snapshots[0].eps_low == 1.10
    assert eps_result.snapshots[0].analyst_count == 12

    assert revenue_result.errors == []
    assert revenue_result.snapshots[0].ticker == "NTNX"
    assert revenue_result.snapshots[0].revenue_average == 1_234_567_890.0
    assert revenue_result.snapshots[0].revenue_high == 1_300_000_000.0
    assert revenue_result.snapshots[0].revenue_low == 1_200_000_000.0
    assert revenue_result.snapshots[0].analyst_count == 10
    assert [call["params"]["freq"] for call in client.calls] == ["quarterly", "quarterly"]


def test_missing_token_returns_error_without_http_call() -> None:
    from prescient.data import DataProvider, DataProviderErrorType, FinnhubEarningsAdapter

    client = FakeHttpClient(FakeHttpResponse(payload=[]))
    adapter = FinnhubEarningsAdapter(token="", http_client=client)

    result = adapter.get_company_earnings("ntnx")

    assert result.snapshots == []
    assert len(result.errors) == 1
    assert result.errors[0].provider == DataProvider.FINNHUB
    assert result.errors[0].error_type == DataProviderErrorType.MISSING_API_KEY
    assert result.errors[0].symbol == "NTNX"
    assert client.calls == []


def test_provider_http_errors_map_to_structured_error_types() -> None:
    from prescient.data import DataProviderErrorType, FinnhubEarningsAdapter

    cases = [
        (401, DataProviderErrorType.UNAUTHORIZED),
        (403, DataProviderErrorType.UNAUTHORIZED),
        (402, DataProviderErrorType.PAYMENT_REQUIRED),
        (404, DataProviderErrorType.UNSUPPORTED_SYMBOL),
        (429, DataProviderErrorType.RATE_LIMITED),
        (500, DataProviderErrorType.PROVIDER_UNAVAILABLE),
        (503, DataProviderErrorType.PROVIDER_UNAVAILABLE),
    ]

    for status_code, expected_error in cases:
        adapter = FinnhubEarningsAdapter(
            token="secret-token",
            http_client=FakeHttpClient(FakeHttpResponse(status_code=status_code, payload={})),
        )

        result = adapter.get_company_earnings("ntnx")

        assert result.snapshots == []
        assert [error.error_type for error in result.errors] == [expected_error]
        assert result.errors[0].status_code == status_code


def test_timeout_malformed_empty_and_unsupported_payload_errors_are_structured() -> None:
    from prescient.data import DataProviderErrorType, FinnhubEarningsAdapter

    timeout_adapter = FinnhubEarningsAdapter(
        token="secret-token",
        http_client=FakeHttpClient(TimeoutError("timed out")),
    )
    malformed_json_adapter = FinnhubEarningsAdapter(
        token="secret-token",
        http_client=FakeHttpClient(
            FakeHttpResponse(payload=None, json_error=ValueError("bad json"))
        ),
    )
    unsupported_shape_adapter = FinnhubEarningsAdapter(
        token="secret-token",
        http_client=FakeHttpClient(FakeHttpResponse(payload={"unexpected": []})),
    )
    empty_adapter = FinnhubEarningsAdapter(
        token="secret-token",
        http_client=FakeHttpClient(FakeHttpResponse(payload={"earningsCalendar": []})),
    )

    assert timeout_adapter.get_company_earnings("NTNX").errors[0].error_type == (
        DataProviderErrorType.TIMEOUT
    )
    assert malformed_json_adapter.get_company_earnings("NTNX").errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert unsupported_shape_adapter.get_company_earnings("NTNX").errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert empty_adapter.get_earnings_calendar(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 3),
    ).errors[0].error_type == DataProviderErrorType.EMPTY_RESPONSE


def test_serialized_provider_errors_are_journal_safe() -> None:
    from prescient.data import FinnhubEarningsAdapter

    adapter = FinnhubEarningsAdapter(
        token="secret-token-123",
        http_client=FakeHttpClient(
            FakeHttpResponse(status_code=429, payload={"token": "secret-token-123"})
        ),
    )

    serialized = adapter.get_company_earnings("NTNX").errors[0].model_dump(mode="json")
    rendered = repr(serialized).lower()

    assert "secret-token-123" not in rendered
    assert "authorization" not in rendered
    assert "raw_payload" not in rendered
    assert "prompt" not in rendered
    assert "broker" not in rendered
    assert "account_id" not in rendered
