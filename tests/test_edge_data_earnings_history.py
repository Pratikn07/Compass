from __future__ import annotations

from datetime import date
from typing import Any


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class FakeClient:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        return FakeResponse(self._payload)


_MU_PAYLOAD = {
    "symbol": "MU",
    "quarterlyEarnings": [
        {
            "fiscalDateEnding": "2024-05-31",
            "reportedDate": "2024-06-26",
            "reportedEPS": "1.45",
            "estimatedEPS": "1.20",
            "surprise": "0.25",
            "surprisePercentage": "20.83",
            "reportTime": "post-market",
        },
        {
            "fiscalDateEnding": "2023-02-28",
            "reportedDate": "2023-03-28",
            "reportedEPS": "-1.91",
            "estimatedEPS": "-0.86",
            "surprise": "-1.05",
            "surprisePercentage": "-122.0",
            "reportTime": "post-market",
        },
    ],
}


def test_maps_quarterly_rows_and_filters_window() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    adapter = AlphaVantageEarningsHistoryAdapter(
        api_key="k", http_client=FakeClient(_MU_PAYLOAD)
    )
    anns, errors = adapter.get_earnings_history(
        tickers=["mu"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert errors == []
    assert len(anns) == 1  # 2023 row filtered out
    a = anns[0]
    assert a.ticker == "MU"
    assert a.report_date == date(2024, 6, 26)
    assert a.report_time == "AMC"  # "post-market" -> AMC
    assert a.eps_actual == 1.45
    assert a.eps_estimate == 1.20
    assert a.surprise_pct == 20.83


def test_missing_key_returns_error_no_call() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    client = FakeClient(_MU_PAYLOAD)
    adapter = AlphaVantageEarningsHistoryAdapter(api_key="", http_client=client)
    anns, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert anns == []
    assert len(errors) == 1
    assert client.calls == []


def test_rate_limit_note_becomes_error() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    note = {"Information": "rate limit reached, please subscribe"}
    adapter = AlphaVantageEarningsHistoryAdapter(api_key="k", http_client=FakeClient(note))
    anns, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert anns == []
    assert len(errors) == 1
    assert "secret" not in repr(errors[0]).lower()


def test_secret_not_leaked_in_errors() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    note = {"Note": "Thank you for using Alpha Vantage"}
    adapter = AlphaVantageEarningsHistoryAdapter(
        api_key="super-secret-key", http_client=FakeClient(note)
    )
    _, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert "super-secret-key" not in repr([e.model_dump(mode="json") for e in errors])
