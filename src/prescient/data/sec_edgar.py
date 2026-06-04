from __future__ import annotations

from datetime import datetime
from typing import Any
from prescient.data.models import (
    DataProvider,
    DataProviderError,
    DataProviderErrorType,
    XBRLMetric,
    CompanyFactsResult,
    SecFiling,
    FilingHistoryResult,
    CompanyConceptResult,
)


class SecEdgarFundamentalsAdapter:
    def __init__(self, user_agent: str, http_client: Any) -> None:
        self.user_agent = user_agent.strip()
        self.http_client = http_client

    def _check_user_agent(self, provider: DataProvider) -> DataProviderError | None:
        if not self.user_agent:
            return DataProviderError(
                provider=provider,
                error_type=DataProviderErrorType.MISSING_USER_AGENT,
                message="SEC requests require a configured descriptive User-Agent",
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
        symbol: str | None = None,
    ) -> DataProviderError:
        if status_code == 404:
            error_type = DataProviderErrorType.UNSUPPORTED_SYMBOL
            message = "Unsupported symbol or CIK not found"
        elif status_code in (401, 403):
            error_type = DataProviderErrorType.UNAUTHORIZED
            message = "Unauthorized access to SEC API"
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

    def get_company_facts(
        self, 
        cik: str | int, 
        ticker: str | None = None, 
        fetched_at: datetime | None = None
    ) -> CompanyFactsResult:
        provider = DataProvider.SEC_EDGAR
        ua_error = self._check_user_agent(provider)
        if ua_error:
            return CompanyFactsResult(errors=[ua_error])

        cik_str = str(cik).strip().zfill(10)
        ticker_upper = ticker.strip().upper() if ticker is not None else "UNKNOWN"
        source_endpoint = f"/api/xbrl/companyfacts/CIK{cik_str}.json"
        url = f"https://data.sec.gov{source_endpoint}"

        try:
            response = self.http_client.get(
                url,
                params={},
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=10.0,
            )
        except Exception as e:
            return CompanyFactsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return CompanyFactsResult(
                errors=[self._handle_response_error(response.status_code, provider, source_endpoint, ticker_upper)]
            )

        try:
            payload = response.json()
        except Exception as e:
            return CompanyFactsResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        metrics: list[XBRLMetric] = []
        facts = payload.get("facts", {})
        cik_int = str(int(cik))

        for taxonomy, concepts in facts.items():
            for concept, concept_data in concepts.items():
                for unit, entries in concept_data.get("units", {}).items():
                    for entry in entries:
                        val = entry.get("val")
                        # Skip if value is not numeric
                        try:
                            val_float = float(val)
                        except (ValueError, TypeError):
                            continue

                        accn = entry.get("accn")
                        accn_clean = accn.replace("-", "")
                        source_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_clean}/{accn}-index.html"

                        metrics.append(
                            XBRLMetric(
                                provider=provider,
                                source_endpoint=source_endpoint,
                                ticker=ticker_upper,
                                cik=cik_str,
                                metric_name=concept,
                                taxonomy=taxonomy,
                                concept=concept,
                                value=val_float,
                                unit=unit,
                                period=entry.get("end"),
                                fiscal_year=entry.get("fy"),
                                fiscal_period=entry.get("fp"),
                                filing_form=entry.get("form"),
                                accession_number=accn,
                                source_url=source_url,
                                fetched_at=fetched_at,
                            )
                        )

        return CompanyFactsResult(metrics=metrics)

    def get_filing_history(
        self, 
        cik: str | int, 
        ticker: str | None = None, 
        fetched_at: datetime | None = None
    ) -> FilingHistoryResult:
        provider = DataProvider.SEC_EDGAR
        ua_error = self._check_user_agent(provider)
        if ua_error:
            return FilingHistoryResult(errors=[ua_error])

        cik_str = str(cik).strip().zfill(10)
        ticker_upper = ticker.strip().upper() if ticker is not None else "UNKNOWN"
        source_endpoint = f"/submissions/CIK{cik_str}.json"
        url = f"https://data.sec.gov{source_endpoint}"

        try:
            response = self.http_client.get(
                url,
                params={},
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=10.0,
            )
        except Exception as e:
            return FilingHistoryResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return FilingHistoryResult(
                errors=[self._handle_response_error(response.status_code, provider, source_endpoint, ticker_upper)]
            )

        try:
            payload = response.json()
        except Exception as e:
            return FilingHistoryResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        filings: list[SecFiling] = []
        recent = payload.get("filings", {}).get("recent", {})
        cik_int = str(int(cik))

        accns = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        forms = recent.get("form", [])

        for i in range(len(accns)):
            accn = accns[i]
            accn_clean = accn.replace("-", "")
            source_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_clean}/{accn}-index.html"

            filings.append(
                SecFiling(
                    form_type=forms[i],
                    accession_number=accn,
                    ticker=ticker_upper,
                    cik=cik_str,
                    filing_date=filing_dates[i],
                    report_period=report_dates[i],
                    provider=provider,
                    source_url=source_url,
                )
            )

        return FilingHistoryResult(filings=filings)

    def get_company_concept(
        self,
        cik: str | int,
        taxonomy: str,
        concept: str,
        ticker: str | None = None,
        fetched_at: datetime | None = None,
    ) -> CompanyConceptResult:
        provider = DataProvider.SEC_EDGAR
        ua_error = self._check_user_agent(provider)
        if ua_error:
            return CompanyConceptResult(errors=[ua_error])

        cik_str = str(cik).strip().zfill(10)
        ticker_upper = ticker.strip().upper() if ticker is not None else "UNKNOWN"
        source_endpoint = f"/api/xbrl/companyconcept/CIK{cik_str}/{taxonomy}/{concept}.json"
        url = f"https://data.sec.gov{source_endpoint}"

        try:
            response = self.http_client.get(
                url,
                params={},
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=10.0,
            )
        except Exception as e:
            return CompanyConceptResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        if response.status_code != 200:
            return CompanyConceptResult(
                errors=[self._handle_response_error(response.status_code, provider, source_endpoint, ticker_upper)]
            )

        try:
            payload = response.json()
        except Exception as e:
            return CompanyConceptResult(
                errors=[self._handle_request_error(e, provider, source_endpoint, ticker_upper)]
            )

        metrics: list[XBRLMetric] = []
        cik_int = str(int(cik))
        tag = payload.get("tag", concept)

        for unit, entries in payload.get("units", {}).items():
            for entry in entries:
                val = entry.get("val")
                try:
                    val_float = float(val)
                except (ValueError, TypeError):
                    continue

                accn = entry.get("accn")
                accn_clean = accn.replace("-", "")
                source_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_clean}/{accn}-index.html"

                metrics.append(
                    XBRLMetric(
                        provider=provider,
                        source_endpoint=source_endpoint,
                        ticker=ticker_upper,
                        cik=cik_str,
                        metric_name=tag,
                        taxonomy=taxonomy,
                        concept=tag,
                        value=val_float,
                        unit=unit,
                        period=entry.get("end"),
                        fiscal_year=entry.get("fy"),
                        fiscal_period=entry.get("fp"),
                        filing_form=entry.get("form"),
                        accession_number=accn,
                        source_url=source_url,
                        fetched_at=fetched_at,
                    )
                )

        return CompanyConceptResult(metrics=metrics)
