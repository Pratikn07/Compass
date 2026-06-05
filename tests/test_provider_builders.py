from __future__ import annotations

from typing import Any

from prescient.data.alpha_vantage import AlphaVantageNewsSentimentAdapter
from prescient.data.config import ProviderConfig
from prescient.data.finnhub import FinnhubEarningsAdapter
from prescient.data.fmp import FmpStockPeersAdapter
from prescient.data.providers import (
    build_alpha_vantage_adapter,
    build_finnhub_adapter,
    build_fmp_adapter,
    build_sec_edgar_adapter,
)
from prescient.data.sec_edgar import SecEdgarFundamentalsAdapter


class _FakeHttp:
    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no live call expected in builder tests")


def _full_config() -> ProviderConfig:
    return ProviderConfig.from_env(
        {
            "FINNHUB_API_KEY": "fk",
            "FMP_API_KEY": "fmpk",
            "ALPHAVANTAGE_API_KEY": "avk",
            "SEC_EDGAR_USER_AGENT": "prescient research test@example.com",
        }
    )


def test_build_finnhub_adapter_when_key_present() -> None:
    adapter = build_finnhub_adapter(_full_config(), http_client=_FakeHttp())
    assert isinstance(adapter, FinnhubEarningsAdapter)
    assert adapter.token == "fk"


def test_build_fmp_adapter_when_key_present() -> None:
    adapter = build_fmp_adapter(_full_config(), http_client=_FakeHttp())
    assert isinstance(adapter, FmpStockPeersAdapter)


def test_build_alpha_vantage_adapter_when_key_present() -> None:
    adapter = build_alpha_vantage_adapter(_full_config(), http_client=_FakeHttp())
    assert isinstance(adapter, AlphaVantageNewsSentimentAdapter)


def test_build_sec_edgar_adapter_when_user_agent_present() -> None:
    adapter = build_sec_edgar_adapter(_full_config(), http_client=_FakeHttp())
    assert isinstance(adapter, SecEdgarFundamentalsAdapter)
    assert adapter.user_agent == "prescient research test@example.com"


def test_builders_return_none_when_credential_absent() -> None:
    empty = ProviderConfig.from_env({})
    assert build_finnhub_adapter(empty, http_client=_FakeHttp()) is None
    assert build_fmp_adapter(empty, http_client=_FakeHttp()) is None
    assert build_alpha_vantage_adapter(empty, http_client=_FakeHttp()) is None
    assert build_sec_edgar_adapter(empty, http_client=_FakeHttp()) is None
