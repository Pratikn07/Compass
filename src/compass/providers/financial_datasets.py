from __future__ import annotations

import httpx

from compass.providers.base import (
    ProviderResult,
    missing_configuration,
    request_error,
    status_error,
)


class FinancialDatasetsProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        client=None,
        base_url: str = "https://api.financialdatasets.ai",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.client = client or httpx.Client()
        self.base_url = base_url.rstrip("/")

    def financials(self, ticker: str) -> ProviderResult:
        if not self.api_key:
            return missing_configuration("financial_datasets")
        symbol = ticker.strip().upper()
        try:
            response = self.client.get(
                f"{self.base_url}/financials",
                params={"ticker": symbol, "period": "quarterly", "limit": 8},
                headers={"X-API-KEY": self.api_key},
                timeout=10.0,
            )
        except Exception:
            return request_error("financial_datasets")
        if response.status_code != 200:
            return status_error("financial_datasets", response.status_code)
        payload = response.json()
        financials = payload.get("financials") if isinstance(payload, dict) else None
        if not isinstance(financials, dict):
            return request_error("financial_datasets")
        items = []
        metadata = {"ticker", "report_period", "fiscal_period", "currency"}
        for statement_type, rows in financials.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for metric_name, value in row.items():
                    if metric_name in metadata:
                        continue
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue
                    items.append(
                        {
                            "ticker": str(row.get("ticker") or symbol).upper(),
                            "statement_type": statement_type,
                            "metric_name": metric_name,
                            "value": numeric,
                            "report_period": row.get("report_period"),
                        }
                    )
        return ProviderResult(items=items)
