from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from prescient.data import DataProvider, DataProviderErrorType
from prescient.data.fmp import FmpMarketDataAdapter


R5B_PRD_PATH = Path("docs/prd/05-live-data-r5b-input-assembly-layer-prd.md")


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
    def __init__(self, response: FakeHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_r5b_prd_is_saved_for_live_input_assembly() -> None:
    prd = R5B_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R5B Live Data Input Assembly Layer" in prd
    assert "FmpMarketDataAdapter" in prd
    assert "assemble_pipeline_inputs" in prd
    assert "Phase C owns options-chain provider" in prd


def test_historical_price_response_normalizes_candles_and_request() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload=[
                {
                    "symbol": "ntnx",
                    "date": "2026-05-29",
                    "open": "100.50",
                    "high": "105.00",
                    "low": "99.25",
                    "close": "104.00",
                    "volume": "2000000",
                    "vwap": "103.25",
                    "change": "3.50",
                    "changePercent": "3.48",
                }
            ]
        )
    )
    fetched_at = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    adapter = FmpMarketDataAdapter(api_key="secret-key", http_client=client)

    result = adapter.get_historical_prices(
        "ntnx",
        date_from=date(2026, 5, 1),
        date_to=date(2026, 6, 1),
        fetched_at=fetched_at,
    )

    assert result.errors == []
    assert len(result.candles) == 1
    candle = result.candles[0]
    assert candle.ticker == "NTNX"
    assert candle.trading_date == date(2026, 5, 29)
    assert candle.open == 100.50
    assert candle.high == 105.00
    assert candle.low == 99.25
    assert candle.close == 104.00
    assert candle.volume == 2_000_000
    assert candle.vwap == 103.25
    assert candle.provider == DataProvider.FMP
    assert candle.source_endpoint == "/historical-price-eod/full"
    assert candle.fetched_at == fetched_at
    assert client.calls == [
        {
            "url": "https://financialmodelingprep.com/stable/historical-price-eod/full",
            "params": {
                "symbol": "NTNX",
                "from": "2026-05-01",
                "to": "2026-06-01",
                "apikey": "secret-key",
            },
            "timeout": 10.0,
        }
    ]


def test_historical_price_errors_are_structured_and_secret_safe() -> None:
    missing_key = FmpMarketDataAdapter(
        api_key="",
        http_client=FakeHttpClient(FakeHttpResponse(payload=[])),
    )
    unauthorized = FmpMarketDataAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(status_code=403, payload={"apikey": "secret-key"})
        ),
    )
    malformed = FmpMarketDataAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload=None, json_error=ValueError("bad"))),
    )

    assert missing_key.get_historical_prices(
        "AAPL",
        date_from=date(2026, 5, 1),
        date_to=date(2026, 6, 1),
    ).errors[0].error_type == DataProviderErrorType.MISSING_API_KEY
    assert unauthorized.get_historical_prices(
        "AAPL",
        date_from=date(2026, 5, 1),
        date_to=date(2026, 6, 1),
    ).errors[0].error_type == DataProviderErrorType.UNAUTHORIZED

    error = malformed.get_historical_prices(
        "AAPL",
        date_from=date(2026, 5, 1),
        date_to=date(2026, 6, 1),
    ).errors[0]
    assert error.error_type == DataProviderErrorType.MALFORMED_RESPONSE
    assert "secret-key" not in repr(error.model_dump(mode="json"))
