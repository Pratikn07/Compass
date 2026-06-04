from __future__ import annotations

import pytest
from prescient.data import (
    get_earnings_provider,
    get_peer_provider,
    get_news_provider,
    get_fundamentals_provider,
    FinnhubEarningsAdapter,
    FmpStockPeersAdapter,
    AlphaVantageNewsSentimentAdapter,
    SecEdgarFundamentalsAdapter,
    FinancialDatasetsFundamentalsAdapter,
    DaloopaFundamentalsAdapter,
)


class MockClient:
    pass


def test_peer_provider_factory_resolution() -> None:
    client = MockClient()
    adapter = get_peer_provider("fmp", api_key="secret", http_client=client)
    assert isinstance(adapter, FmpStockPeersAdapter)
    assert adapter._api_key == "secret"
    assert adapter._http_client is client

    with pytest.raises(ValueError, match="Unknown peer provider: invalid"):
        get_peer_provider("invalid", api_key="secret")


def test_earnings_provider_factory_resolution() -> None:
    client = MockClient()
    adapter = get_earnings_provider("finnhub", token="secret", http_client=client)
    assert isinstance(adapter, FinnhubEarningsAdapter)
    assert adapter.token == "secret"
    assert adapter.http_client is client

    with pytest.raises(ValueError, match="Unknown earnings provider: invalid"):
        get_earnings_provider("invalid", token="secret")


def test_news_provider_factory_resolution() -> None:
    client = MockClient()
    adapter = get_news_provider("alpha_vantage", api_key="secret", http_client=client)
    assert isinstance(adapter, AlphaVantageNewsSentimentAdapter)
    assert adapter._api_key == "secret"
    assert adapter._http_client is client

    with pytest.raises(ValueError, match="Unknown news provider: invalid"):
        get_news_provider("invalid", api_key="secret")


def test_fundamentals_provider_factory_resolution() -> None:
    client = MockClient()
    
    # Test SEC Edgar
    sec_adapter = get_fundamentals_provider("sec_edgar", user_agent="agent", http_client=client)
    assert isinstance(sec_adapter, SecEdgarFundamentalsAdapter)
    assert sec_adapter.user_agent == "agent"

    # Test Financial Datasets
    fd_adapter = get_fundamentals_provider("financial_datasets", api_key="key", http_client=client)
    assert isinstance(fd_adapter, FinancialDatasetsFundamentalsAdapter)
    assert fd_adapter.api_key == "key"

    # Test Daloopa
    daloopa_adapter = get_fundamentals_provider("daloopa", api_key="key", kpi_endpoint="end", http_client=client)
    assert isinstance(daloopa_adapter, DaloopaFundamentalsAdapter)
    assert daloopa_adapter.api_key == "key"
    assert daloopa_adapter.kpi_endpoint == "end"

    with pytest.raises(ValueError, match="Unknown fundamentals provider: invalid"):
        get_fundamentals_provider("invalid")
