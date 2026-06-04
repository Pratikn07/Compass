from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prescient.data import (
    DataProvider,
    DataProviderErrorType,
    FmpStockPeersAdapter,
    PeerListSnapshot,
    filter_peers_to_theme,
    filter_peers_to_universe,
)
from prescient.signal.models import StrategyUniverse, ThemeConfig


R4_2_PRD_PATH = Path("docs/prd/04-data-r4-2-fmp-stock-peers-prd.md")


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


def _universe() -> StrategyUniverse:
    return StrategyUniverse(
        themes=[
            ThemeConfig(
                name="AI_STORAGE",
                tickers=["NTNX", "PSTG", "NTAP", "WDC"],
                drivers=["AI data center demand"],
            ),
            ThemeConfig(
                name="MEGA_CAP_TECH",
                tickers=["AAPL", "MSFT", "NVDA"],
                drivers=["platform AI capex"],
            ),
        ]
    )


def test_r4_2_prd_is_saved_and_preserves_configured_themes_as_source_of_truth() -> None:
    prd = R4_2_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R4.2 FMP Stock Peers / Competitor Lists" in prd
    assert "Financial Modeling Prep" in prd
    assert "FMP peers must not automatically replace or expand `config/themes.yaml`" in prd
    assert "enrichment only" in prd
    assert "No automatic theme generation" in prd


def test_single_ticker_response_normalizes_stock_peer_snapshot() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload=[
                {
                    "symbol": "aapl",
                    "peers": ["msft", "NVDA", " ", "aapl", "MSFT", None],
                }
            ]
        )
    )
    fetched_at = datetime(2026, 6, 3, 17, 30, tzinfo=timezone.utc)
    adapter = FmpStockPeersAdapter(api_key="secret-key", http_client=client)

    result = adapter.get_stock_peers("aapl", fetched_at=fetched_at)

    assert result.errors == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.ticker == "AAPL"
    assert snapshot.peers == ["MSFT", "NVDA"]
    assert snapshot.provider == DataProvider.FMP
    assert snapshot.source_endpoint == "/stock-peers"
    assert snapshot.fetched_at == fetched_at
    assert client.calls == [
        {
            "url": "https://financialmodelingprep.com/stable/stock-peers",
            "params": {"symbol": "AAPL", "apikey": "secret-key"},
            "timeout": 10.0,
        }
    ]


def test_legacy_peers_list_response_shape_is_accepted() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload=[
                {
                    "symbol": "AAPL",
                    "peersList": ["MSFT", "NVDA", "ASML"],
                }
            ]
        )
    )
    adapter = FmpStockPeersAdapter(api_key="secret-key", http_client=client)

    result = adapter.get_stock_peers("aapl")

    assert result.errors == []
    assert result.snapshots[0].ticker == "AAPL"
    assert result.snapshots[0].peers == ["MSFT", "NVDA", "ASML"]


def test_bulk_response_normalizes_multiple_peer_snapshots() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload=[
                {"symbol": "aapl", "peers": ["msft", "nvda"]},
                {"symbol": "ntnx", "peersList": ["pstg", "ntap", "ntnx"]},
            ]
        )
    )
    adapter = FmpStockPeersAdapter(api_key="secret-key", http_client=client)

    result = adapter.get_bulk_stock_peers()

    assert result.errors == []
    assert [snapshot.ticker for snapshot in result.snapshots] == ["AAPL", "NTNX"]
    assert result.snapshots[0].peers == ["MSFT", "NVDA"]
    assert result.snapshots[1].peers == ["PSTG", "NTAP"]
    assert client.calls == [
        {
            "url": "https://financialmodelingprep.com/stable/peers-bulk",
            "params": {"apikey": "secret-key"},
            "timeout": 10.0,
        }
    ]


def test_missing_api_key_returns_error_without_http_call() -> None:
    client = FakeHttpClient(FakeHttpResponse(payload=[]))
    adapter = FmpStockPeersAdapter(api_key="", http_client=client)

    result = adapter.get_stock_peers("AAPL")

    assert result.snapshots == []
    assert len(result.errors) == 1
    assert result.errors[0].error_type == DataProviderErrorType.MISSING_API_KEY
    assert client.calls == []


def test_provider_http_errors_map_to_structured_error_types() -> None:
    cases = [
        (401, DataProviderErrorType.UNAUTHORIZED),
        (403, DataProviderErrorType.UNAUTHORIZED),
        (429, DataProviderErrorType.RATE_LIMITED),
        (500, DataProviderErrorType.PROVIDER_UNAVAILABLE),
        (503, DataProviderErrorType.PROVIDER_UNAVAILABLE),
    ]

    for status_code, expected_error in cases:
        adapter = FmpStockPeersAdapter(
            api_key="secret-key",
            http_client=FakeHttpClient(
                FakeHttpResponse(status_code=status_code, payload={"error": "provider error"})
            ),
        )

        result = adapter.get_stock_peers("AAPL")

        assert result.snapshots == []
        assert [error.error_type for error in result.errors] == [expected_error]
        assert result.errors[0].status_code == status_code


def test_timeout_malformed_empty_and_unsupported_symbol_errors_are_structured() -> None:
    timeout_adapter = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(TimeoutError("request timed out")),
    )
    malformed_adapter = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(payload=None, json_error=ValueError("bad json"))
        ),
    )
    empty_adapter = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload=[])),
    )
    unsupported_adapter = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(status_code=404, payload={})),
    )

    assert timeout_adapter.get_stock_peers("AAPL").errors[0].error_type == (
        DataProviderErrorType.TIMEOUT
    )
    assert malformed_adapter.get_stock_peers("AAPL").errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert empty_adapter.get_stock_peers("AAPL").errors[0].error_type == (
        DataProviderErrorType.EMPTY_RESPONSE
    )
    assert unsupported_adapter.get_stock_peers("AAPL").errors[0].error_type == (
        DataProviderErrorType.UNSUPPORTED_SYMBOL
    )


def test_serialized_provider_errors_are_journal_safe() -> None:
    adapter = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(status_code=429, payload={"apikey": "secret-key"})
        ),
    )

    serialized = adapter.get_stock_peers("AAPL").errors[0].model_dump(mode="json")
    rendered = repr(serialized).lower()

    assert serialized["provider"] == "fmp"
    assert serialized["symbol"] == "AAPL"
    assert "secret-key" not in rendered
    assert "authorization" not in rendered
    assert "raw_payload" not in rendered
    assert "prompt" not in rendered
    assert "broker" not in rendered
    assert "account_id" not in rendered


def test_theme_and_universe_filtering_only_keeps_configured_tickers() -> None:
    snapshot = PeerListSnapshot(
        ticker="ntnx",
        peers=["pstg", "msft", "ntap", "tsla", "wdc"],
        provider=DataProvider.FMP,
        source_endpoint="/stock-peers",
    )

    theme_filtered = filter_peers_to_theme(snapshot, _universe(), "ai_storage")
    universe_filtered = filter_peers_to_universe(snapshot, _universe())

    assert theme_filtered.peers == ["PSTG", "NTAP", "WDC"]
    assert universe_filtered.peers == ["PSTG", "MSFT", "NTAP", "WDC"]
    assert snapshot.peers == ["PSTG", "MSFT", "NTAP", "TSLA", "WDC"]


def test_filtering_does_not_mutate_original_snapshot_or_universe() -> None:
    universe = _universe()
    original_universe = universe.model_dump(mode="json")
    snapshot = PeerListSnapshot(
        ticker="NTNX",
        peers=["PSTG", "MSFT", "NTAP"],
        provider=DataProvider.FMP,
        source_endpoint="/stock-peers",
    )
    original_snapshot = snapshot.model_dump(mode="json")

    filter_peers_to_theme(snapshot, universe, "AI_STORAGE")
    filter_peers_to_universe(snapshot, universe)

    assert snapshot.model_dump(mode="json") == original_snapshot
    assert universe.model_dump(mode="json") == original_universe


def test_same_fake_response_serializes_deterministically() -> None:
    response = FakeHttpResponse(payload=[{"symbol": "aapl", "peers": ["msft", "nvda"]}])
    first = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(response),
    ).get_stock_peers("AAPL")
    second = FmpStockPeersAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(response),
    ).get_stock_peers("AAPL")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
