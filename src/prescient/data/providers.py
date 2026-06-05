"""Factory helpers that build each data adapter from a ProviderConfig.

Each returns None when its credential is absent, so callers treat the provider as
unavailable rather than constructing a broken adapter. Adapter internals are
unchanged — these only wire config -> constructor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from prescient.data.alpaca_market import AlpacaMarketDataAdapter

from prescient.data.alpha_vantage import AlphaVantageNewsSentimentAdapter
from prescient.data.config import ProviderConfig
from prescient.data.finnhub import FinnhubEarningsAdapter
from prescient.data.fmp import FmpMarketDataAdapter, FmpStockPeersAdapter
from prescient.data.sec_edgar import SecEdgarFundamentalsAdapter


class _SecHttpClient:
    """Default transport for the SEC adapter, which passes a `headers` kwarg
    (User-Agent is required by SEC). The Finnhub/FMP default clients do not accept
    headers, so SEC needs its own.
    """

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> httpx.Response:
        return httpx.get(url, params=params or {}, headers=headers or {}, timeout=timeout)


def build_finnhub_adapter(
    config: ProviderConfig,
    http_client: Any | None = None,
    *,
    prefer_broad_calendar: bool = False,
) -> FinnhubEarningsAdapter | None:
    if not config.has("finnhub"):
        return None
    return FinnhubEarningsAdapter(
        token=config.finnhub_api_key,
        http_client=http_client,
        prefer_broad_calendar=prefer_broad_calendar,
    )


def build_fmp_adapter(
    config: ProviderConfig,
    http_client: Any | None = None,
) -> FmpStockPeersAdapter | None:
    if not config.has("fmp"):
        return None
    return FmpStockPeersAdapter(
        api_key=config.fmp_api_key,
        http_client=http_client,
    )


def build_fmp_market_data_adapter(
    config: ProviderConfig,
    http_client: Any | None = None,
) -> FmpMarketDataAdapter | None:
    if not config.has("fmp"):
        return None
    return FmpMarketDataAdapter(
        api_key=config.fmp_api_key,
        http_client=http_client,
    )


def build_alpaca_market_data_adapter(
    config: ProviderConfig,
    *,
    option_chain_reader: Any | None = None,
    daily_bars_reader: Any | None = None,
) -> "AlpacaMarketDataAdapter | None":
    """Build the read-only Alpaca market-data adapter when both creds are present.

    Readers are injected (tests, or the live_data layer's SDK readers). The data
    package never imports the Alpaca SDK itself — SDK-bound readers are built in
    prescient.live_data.alpaca_readers and passed in.
    """
    from prescient.data.alpaca_market import AlpacaMarketDataAdapter

    if not config.has("alpaca"):
        return None

    return AlpacaMarketDataAdapter(
        option_chain_reader=option_chain_reader,
        daily_bars_reader=daily_bars_reader,
    )


def build_alpha_vantage_adapter(
    config: ProviderConfig,
    http_client: Any | None = None,
) -> AlphaVantageNewsSentimentAdapter | None:
    if not config.has("alphavantage"):
        return None
    return AlphaVantageNewsSentimentAdapter(
        api_key=config.alphavantage_api_key,
        http_client=http_client,
    )


def build_sec_edgar_adapter(
    config: ProviderConfig,
    http_client: Any | None = None,
) -> SecEdgarFundamentalsAdapter | None:
    if not config.has("sec_edgar"):
        return None
    # SEC adapter requires an http_client that accepts a `headers` kwarg (it sends
    # the required User-Agent). Use the SEC-specific default when none is supplied.
    client = http_client if http_client is not None else _SecHttpClient()
    return SecEdgarFundamentalsAdapter(
        user_agent=config.sec_edgar_user_agent or "",
        http_client=client,
    )
