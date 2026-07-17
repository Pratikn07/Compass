from __future__ import annotations

import httpx

from compass.providers.base import (
    ProviderResult,
    missing_configuration,
    request_error,
    status_error,
)


class DaloopaProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: str | None,
        client=None,
        base_url: str = "https://api.daloopa.com",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.endpoint = (endpoint or "").strip()
        self.client = client or httpx.Client()
        self.base_url = base_url.rstrip("/")

    def kpis(self, ticker: str) -> ProviderResult:
        if not self.api_key or not self.endpoint:
            return missing_configuration("daloopa")
        symbol = ticker.strip().upper()
        try:
            response = self.client.get(
                f"{self.base_url}{self.endpoint}",
                params={"ticker": symbol, "period": "quarterly", "limit": 8},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
        except Exception:
            return request_error("daloopa")
        if response.status_code != 200:
            return status_error("daloopa", response.status_code)
        payload = response.json()
        rows = payload.get("kpis") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return request_error("daloopa")
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                value = float(row.get("value"))
            except (TypeError, ValueError):
                continue
            items.append(
                {
                    "ticker": str(row.get("ticker") or symbol).upper(),
                    "metric_name": row.get("metric_name"),
                    "value": value,
                    "period": row.get("period"),
                    "unit": row.get("unit"),
                }
            )
        return ProviderResult(items=items)
