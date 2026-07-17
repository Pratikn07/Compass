from __future__ import annotations

import httpx

from compass.providers.base import (
    ProviderResult,
    missing_configuration,
    request_error,
    status_error,
)


class FinnhubProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        client=None,
        base_url: str = "https://finnhub.io/api/v1",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.client = client or httpx.Client()
        self.base_url = base_url.rstrip("/")

    def company_earnings(self, ticker: str) -> ProviderResult:
        if not self.api_key:
            return missing_configuration("finnhub")
        symbol = ticker.strip().upper()
        try:
            response = self.client.get(
                f"{self.base_url}/stock/earnings",
                params={"symbol": symbol, "token": self.api_key},
                timeout=10.0,
            )
        except Exception:
            return request_error("finnhub")
        if response.status_code != 200:
            return status_error("finnhub", response.status_code)
        payload = response.json()
        if not isinstance(payload, list):
            return request_error("finnhub")
        return ProviderResult(
            items=[
                {
                    "ticker": str(row.get("symbol") or symbol).upper(),
                    "actual": row.get("actual"),
                    "estimate": row.get("estimate"),
                    "period": row.get("period"),
                }
                for row in payload
                if isinstance(row, dict)
            ]
        )
