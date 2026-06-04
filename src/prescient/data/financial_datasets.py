from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    FinancialDatasetsMetric,
    FinancialsResult,
    KpiMetric,
    KpiMetricsResult,
    FilingItem,
    FilingItemsResult,
)


class FinancialDatasetsFundamentalsAdapter:
    def __init__(self, api_key: str, http_client: Any) -> None:
        self.api_key = api_key.strip()
        self.http_client = http_client

    def _check_api_key(self, provider: DataProvider) -> DataProviderError | None:
        if not self.api_key:
            return DataProviderError(
                provider=provider,
                error_type=DataProviderErrorType.MISSING_API_KEY,
                message="Missing API Key for Financial Datasets",
            )
        return None

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
        response_headers: dict[str, str] | None = None,
        symbol: str | None = None,
    ) -> DataProviderError:
        retry_after = None
        if status_code == 402:
            error_type = DataProviderErrorType.PAYMENT_REQUIRED
            message = "Payment required / premium tier only"
        elif status_code == 503:
            error_type = DataProviderErrorType.FILING_PARSE_IN_PROGRESS
            message = "Filing parse in progress"
            if response_headers:
                # Case-insensitive header lookup
                headers_lower = {k.lower(): v for k, v in response_headers.items()}
                retry_str = headers_lower.get("retry-after")
                if retry_str:
                    try:
                        retry_after = int(retry_str)
                    except ValueError:
                        pass
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
            retry_after_seconds=retry_after,
        )

    def get_financials(
        self,
        ticker: str,
        period: str = "annual",
        limit: int = 1,
        report_period_lte: str | None = None,
        fetched_at: datetime | None = None,
    ) -> FinancialsResult:
        provider = DataProvider.FINANCIAL_DATASETS
        key_error = self._check_api_key(provider)
        if key_error:
            return FinancialsResult(errors=[key_error])

        ticker_upper = ticker.strip().upper()
        source_endpoint = "/financials"
        url = f"https://api.financialdatasets.ai{source_endpoint}"

        params: dict[str, Any] = {
            "ticker": ticker_upper,
            "period": period,
            "limit": limit,
        }
        if report_period_lte is not None:
            params["report_period_lte"] = report_period_lte

        try:
            response = self.http_client.get(
                url,
                params=params,
                headers={"X-API-KEY": self.api_key},
                timeout=10.0,
            )
        except Exception as e:
            return FinancialsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return FinancialsResult(
                errors=[
                    self._handle_response_error(
                        response.status_code,
                        provider,
                        source_endpoint,
                        getattr(response, "headers", None),
                        ticker_upper,
                    )
                ]
            )

        try:
            payload = response.json()
        except Exception as e:
            return FinancialsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        financials = payload.get("financials", {})
        metrics: list[FinancialDatasetsMetric] = []

        statement_mappings = [
            ("income_statements", "income_statement"),
            ("balance_sheets", "balance_sheet"),
            ("cash_flow_statements", "cash_flow_statement"),
        ]

        metadata_keys = {
            "ticker",
            "report_period",
            "fiscal_period",
            "currency",
            "accession_number",
            "filing_url",
            "note",
            "period",
            "period_type",
        }

        for list_key, statement_type in statement_mappings:
            statement_list = financials.get(list_key, [])
            for statement in statement_list:
                stmt_ticker = statement.get("ticker", ticker_upper).upper()
                stmt_period = statement.get("report_period")
                stmt_fiscal = statement.get("fiscal_period", "FY")
                stmt_currency = statement.get("currency", "USD")
                stmt_accn = statement.get("accession_number")
                stmt_url = statement.get("filing_url")

                for key, val in statement.items():
                    if key in metadata_keys:
                        continue
                    try:
                        val_float = float(val)
                    except (ValueError, TypeError):
                        continue

                    metrics.append(
                        FinancialDatasetsMetric(
                            statement_type=statement_type,
                            metric_name=key,
                            value=val_float,
                            provider=provider,
                            source_endpoint=source_endpoint,
                            ticker=stmt_ticker,
                            unit=stmt_currency,
                            period=stmt_period,
                            fiscal_period=stmt_fiscal,
                            accession_number=stmt_accn,
                            source_url=stmt_url,
                            fetched_at=fetched_at,
                        )
                    )

        return FinancialsResult(metrics=metrics)

    def get_kpi_metrics(
        self,
        ticker: str,
        metric_name: str | None = None,
        period: str = "quarterly",
        limit: int = 4,
        fetched_at: datetime | None = None,
    ) -> KpiMetricsResult:
        provider = DataProvider.FINANCIAL_DATASETS
        key_error = self._check_api_key(provider)
        if key_error:
            return KpiMetricsResult(errors=[key_error])

        ticker_upper = ticker.strip().upper()
        source_endpoint = "/kpi/metrics"
        url = f"https://api.financialdatasets.ai{source_endpoint}"

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
                headers={"X-API-KEY": self.api_key},
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
                        getattr(response, "headers", None),
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

        kpis_list = payload.get("kpi_metrics", [])
        metrics: list[KpiMetric] = []

        for kpi in kpis_list:
            val = kpi.get("value")
            try:
                val_float = float(val)
            except (ValueError, TypeError):
                continue

            yoy_val = kpi.get("yoy_value")
            yoy_val_float = None
            if yoy_val is not None:
                try:
                    yoy_val_float = float(yoy_val)
                except (ValueError, TypeError):
                    pass

            yoy_chg = kpi.get("yoy_change_pct")
            yoy_chg_float = None
            if yoy_chg is not None:
                try:
                    yoy_chg_float = float(yoy_chg)
                except (ValueError, TypeError):
                    pass

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
                    yoy_value=yoy_val_float,
                    yoy_change_pct=yoy_chg_float,
                    source_text=kpi.get("source_text"),
                    source_url=kpi.get("source_url"),
                    fetched_at=fetched_at,
                )
            )

        return KpiMetricsResult(metrics=metrics)

    def get_filing_items(
        self,
        ticker: str,
        filing_type: str = "10-K",
        year: int | None = None,
        items: Sequence[str] | None = None,
        fetched_at: datetime | None = None,
    ) -> FilingItemsResult:
        provider = DataProvider.FINANCIAL_DATASETS
        key_error = self._check_api_key(provider)
        if key_error:
            return FilingItemsResult(errors=[key_error])

        ticker_upper = ticker.strip().upper()
        source_endpoint = "/filings"
        url = f"https://api.financialdatasets.ai{source_endpoint}"

        params: dict[str, Any] = {
            "ticker": ticker_upper,
            "filing_type": filing_type,
        }
        if year is not None:
            params["year"] = year
        if items is not None:
            params["item"] = list(items)

        try:
            response = self.http_client.get(
                url,
                params=params,
                headers={"X-API-KEY": self.api_key},
                timeout=10.0,
            )
        except Exception as e:
            return FilingItemsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return FilingItemsResult(
                errors=[
                    self._handle_response_error(
                        response.status_code,
                        provider,
                        source_endpoint,
                        getattr(response, "headers", None),
                        ticker_upper,
                    )
                ]
            )

        try:
            payload = response.json()
        except Exception as e:
            return FilingItemsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        filing_items: list[FilingItem] = []
        payload_ticker = payload.get("ticker", ticker_upper).upper()
        payload_cik = str(payload.get("cik", "")).strip().zfill(10)
        payload_type = payload.get("filing_type", filing_type)
        payload_accn = payload.get("accession_number", "")

        for item in payload.get("items", []):
            filing_items.append(
                FilingItem(
                    ticker=payload_ticker,
                    cik=payload_cik,
                    filing_type=payload_type,
                    accession_number=payload_accn,
                    item_number=item.get("number"),
                    item_name=item.get("name"),
                    text=item.get("text"),
                    provider=provider,
                    fetched_at=fetched_at,
                )
            )

        return FilingItemsResult(items=filing_items)
