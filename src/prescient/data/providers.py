"""Factory helpers that build each data adapter from a ProviderConfig.

Each returns None when its credential is absent, so callers treat the provider as
unavailable rather than constructing a broken adapter. Adapter internals are
unchanged — these only wire config -> constructor.
"""

from __future__ import annotations

from typing import Any

import httpx

from prescient.data.alpha_vantage import AlphaVantageNewsSentimentAdapter
from prescient.data.config import ProviderConfig
from prescient.data.finnhub import FinnhubEarningsAdapter
from prescient.data.fmp import FmpStockPeersAdapter
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
) -> FinnhubEarningsAdapter | None:
    if not config.has("finnhub"):
        return None
    return FinnhubEarningsAdapter(
        token=config.finnhub_api_key,
        http_client=http_client,
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
