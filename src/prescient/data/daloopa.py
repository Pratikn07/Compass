from __future__ import annotations

from datetime import datetime
from typing import Any
from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    KpiMetric,
    KpiMetricsResult,
)


class DaloopaFundamentalsAdapter:
    def __init__(
        self,
        api_key: str,
        kpi_endpoint: str | None = None,
        http_client: Any = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.kpi_endpoint = kpi_endpoint.strip() if kpi_endpoint else None
        self.http_client = http_client

    def _handle_request_error(
        self, 
        e: Exception, 
        provider: DataProvider, 
        endpoint: str, 
        symbol: str | None = None
    ) -> DataProviderError:
        error_type = DataProviderErrorType.PROVIDER_UNAVAILABLE
        message = str(e)
        status_code = None

        if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
            error_type = DataProviderErrorType.TIMEOUT
        elif isinstance(e, ValueError) or "bad json" in str(e).lower():
            error_type = DataProviderErrorType.MALFORMED_RESPONSE

        return DataProviderError(
            provider=provider,
            error_type=error_type,
            message=message,
            endpoint=endpoint,
            status_code=status_code,
            symbol=symbol,
        )

    def _handle_response_error(
        self,
        status_code: int,
        provider: DataProvider,
        endpoint: str,
        symbol: str | None = None,
    ) -> DataProviderError:
        if status_code == 402:
            error_type = DataProviderErrorType.PAYMENT_REQUIRED
            message = "Payment required / premium tier only"
        elif status_code == 404:
            error_type = DataProviderErrorType.UNSUPPORTED_SYMBOL
            message = "Filing or symbol not supported by provider"
        elif status_code in (401, 403):
            error_type = DataProviderErrorType.UNAUTHORIZED
            message = "Unauthorized access / invalid API key"
        elif status_code == 429:
            error_type = DataProviderErrorType.RATE_LIMITED
            message = "Rate limit exceeded"
        else:
            error_type = DataProviderErrorType.PROVIDER_UNAVAILABLE
            message = f"HTTP Error status code {status_code}"

        return DataProviderError(
            provider=provider,
            error_type=error_type,
            message=message,
            endpoint=endpoint,
            status_code=status_code,
            symbol=symbol,
        )

    def get_kpi_metrics(
        self,
        ticker: str,
        metric_name: str | None = None,
        period: str = "quarterly",
        limit: int = 4,
        fetched_at: datetime | None = None,
    ) -> KpiMetricsResult:
        provider = DataProvider.DALOOPA
        ticker_upper = ticker.strip().upper()

        if not self.kpi_endpoint:
            return KpiMetricsResult(
                errors=[
                    DataProviderError(
                        provider=provider,
                        error_type=DataProviderErrorType.PROVIDER_UNAVAILABLE,
                        message="Daloopa requires a configured customer KPI endpoint",
                        symbol=ticker_upper,
                    )
                ]
            )

        source_endpoint = self.kpi_endpoint
        url = f"https://api.daloopa.com{source_endpoint}"

        params: dict[str, Any] = {
            "ticker": ticker_upper,
            "period": period,
            "limit": limit,
        }
        if metric_name is not None:
            params["metric_name"] = metric_name

        try:
            response = self.http_client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
        except Exception as e:
            return KpiMetricsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return KpiMetricsResult(
                errors=[
                    self._handle_response_error(
                        response.status_code,
                        provider,
                        source_endpoint,
                        ticker_upper,
                    )
                ]
            )

        try:
            payload = response.json()
        except Exception as e:
            return KpiMetricsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        kpis_list = payload.get("kpis", [])
        metrics: list[KpiMetric] = []

        for kpi in kpis_list:
            val = kpi.get("value")
            try:
                val_float = float(val)
            except (ValueError, TypeError):
                continue

            metrics.append(
                KpiMetric(
                    provider=provider,
                    source_endpoint=source_endpoint,
                    ticker=kpi.get("ticker", ticker_upper).upper(),
                    metric_name=kpi.get("metric_name"),
                    value=val_float,
                    unit=kpi.get("unit"),
                    period=kpi.get("period"),
                    period_type=kpi.get("period_type", period),
                    segment=kpi.get("segment"),
                    source_text=kpi.get("source_text"),
                    source_url=kpi.get("source_url"),
                    fetched_at=fetched_at,
                )
            )

        return KpiMetricsResult(metrics=metrics)
