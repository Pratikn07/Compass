from __future__ import annotations

import httpx

from compass.providers.base import (
    ProviderResult,
    missing_configuration,
    request_error,
    status_error,
)


class FmpProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        client=None,
        base_url: str = "https://financialmodelingprep.com/stable",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.client = client or httpx.Client()
        self.base_url = base_url.rstrip("/")

    def stock_peers(self, ticker: str) -> ProviderResult:
        if not self.api_key:
            return missing_configuration("fmp")
        symbol = ticker.strip().upper()
        try:
            response = self.client.get(
                f"{self.base_url}/stock-peers",
                params={"symbol": symbol, "apikey": self.api_key},
                timeout=10.0,
            )
        except Exception:
            return request_error("fmp")
        if response.status_code != 200:
            return status_error("fmp", response.status_code)
        payload = response.json()
        if not isinstance(payload, list):
            return request_error("fmp")
        items = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            peers = row.get("peersList") or row.get("peers") or []
            items.append(
                {
                    "ticker": str(row.get("symbol") or symbol).upper(),
                    "peers": [str(peer).upper() for peer in peers],
                }
            )
        return ProviderResult(items=items)
