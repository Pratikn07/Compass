from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prescient.data import (
    DaloopaFundamentalsAdapter,
    DataProvider,
    DataProviderErrorType,
    FinancialDatasetsFundamentalsAdapter,
    SecEdgarFundamentalsAdapter,
)


R4_5_PRD_PATH = Path("docs/prd/04-data-r4-5-sec-filings-fundamentals-kpis-prd.md")


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
        headers: dict[str, str] | None = None,
    ) -> FakeHttpResponse:
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_r4_5_prd_is_saved_with_tiered_provider_strategy_and_read_only_boundary() -> None:
    prd = R4_5_PRD_PATH.read_text(encoding="utf-8")

    assert "# PRD: R4.5 SEC Filings for Fundamentals & KPIs" in prd
    assert "SEC EDGAR: authoritative public baseline" in prd
    assert "Financial Datasets: normalized fundamentals" in prd
    assert "Daloopa: premium source-linked KPI/fundamental enrichment" in prd
    assert "SEC requests require a configured descriptive `User-Agent`" in prd
    assert "No SEC filing submission API support" in prd


def test_sec_company_facts_normalize_xbrl_fundamental_metrics_with_provenance() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "cik": 320193,
                "entityName": "Apple Inc.",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "label": "Revenue",
                            "units": {
                                "USD": [
                                    {
                                        "fy": 2024,
                                        "fp": "FY",
                                        "form": "10-K",
                                        "filed": "2024-11-01",
                                        "end": "2024-09-28",
                                        "frame": "CY2024",
                                        "val": 391035000000,
                                        "accn": "0000320193-24-000123",
                                    },
                                    {"fy": 2023, "fp": "FY", "val": "not numeric"},
                                ]
                            },
                        }
                    }
                },
            }
        )
    )
    fetched_at = datetime(2026, 6, 3, 18, 30, tzinfo=timezone.utc)
    adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=client,
    )

    result = adapter.get_company_facts(
        cik="320193",
        ticker="aapl",
        fetched_at=fetched_at,
    )

    assert result.errors == []
    assert len(result.metrics) == 1
    metric = result.metrics[0]
    assert metric.provider == DataProvider.SEC_EDGAR
    assert metric.source_endpoint == "/api/xbrl/companyfacts/CIK0000320193.json"
    assert metric.ticker == "AAPL"
    assert metric.cik == "0000320193"
    assert metric.metric_name == "Revenues"
    assert metric.taxonomy == "us-gaap"
    assert metric.concept == "Revenues"
    assert metric.value == 391035000000.0
    assert metric.unit == "USD"
    assert metric.period == "2024-09-28"
    assert metric.fiscal_year == 2024
    assert metric.fiscal_period == "FY"
    assert metric.filing_form == "10-K"
    assert metric.accession_number == "0000320193-24-000123"
    assert metric.source_url == (
        "https://www.sec.gov/Archives/edgar/data/"
        "320193/000032019324000123/0000320193-24-000123-index.html"
    )
    assert metric.fetched_at == fetched_at
    assert client.calls == [
        {
            "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "params": {},
            "headers": {
                "User-Agent": "Prescient pratik@example.com",
                "Accept-Encoding": "gzip, deflate",
            },
            "timeout": 10.0,
        }
    ]


def test_sec_filing_history_normalizes_recent_filings_by_cik() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "filings": {
                    "recent": {
                        "accessionNumber": [
                            "0000320193-24-000123",
                            "0000320193-24-000111",
                        ],
                        "filingDate": ["2024-11-01", "2024-08-02"],
                        "reportDate": ["2024-09-28", "2024-06-29"],
                        "form": ["10-K", "10-Q"],
                    }
                },
            }
        )
    )
    adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=client,
    )

    result = adapter.get_filing_history(cik=320193, ticker="aapl")

    assert result.errors == []
    assert [(filing.form_type, filing.accession_number) for filing in result.filings] == [
        ("10-K", "0000320193-24-000123"),
        ("10-Q", "0000320193-24-000111"),
    ]
    assert result.filings[0].ticker == "AAPL"
    assert result.filings[0].cik == "0000320193"
    assert result.filings[0].filing_date == "2024-11-01"
    assert result.filings[0].report_period == "2024-09-28"
    assert result.filings[0].provider == DataProvider.SEC_EDGAR
    assert result.filings[0].source_url.endswith(
        "/Archives/edgar/data/320193/000032019324000123/"
        "0000320193-24-000123-index.html"
    )


def test_sec_company_concept_uses_taxonomy_and_concept_endpoint() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "cik": 320193,
                "taxonomy": "us-gaap",
                "tag": "NetIncomeLoss",
                "units": {
                    "USD": [
                        {
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "end": "2024-09-28",
                            "val": 93736000000,
                            "accn": "0000320193-24-000123",
                        }
                    ]
                },
            }
        )
    )
    adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=client,
    )

    result = adapter.get_company_concept(
        cik="0000320193",
        taxonomy="us-gaap",
        concept="NetIncomeLoss",
        ticker="aapl",
    )

    assert result.errors == []
    assert result.metrics[0].metric_name == "NetIncomeLoss"
    assert result.metrics[0].concept == "NetIncomeLoss"
    assert result.metrics[0].value == 93736000000.0
    assert client.calls[0]["url"] == (
        "https://data.sec.gov/api/xbrl/companyconcept/"
        "CIK0000320193/us-gaap/NetIncomeLoss.json"
    )


def test_sec_missing_user_agent_returns_structured_error_without_http_call() -> None:
    client = FakeHttpClient(FakeHttpResponse(payload={}))
    adapter = SecEdgarFundamentalsAdapter(user_agent="", http_client=client)

    result = adapter.get_company_facts(cik="320193", ticker="AAPL")

    assert result.metrics == []
    assert result.errors[0].provider == DataProvider.SEC_EDGAR
    assert result.errors[0].error_type == DataProviderErrorType.MISSING_USER_AGENT
    assert client.calls == []


def test_financial_datasets_financials_normalize_statement_metrics() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "financials": {
                    "income_statements": [
                        {
                            "ticker": "nvda",
                            "report_period": "2025-01-26",
                            "fiscal_period": "FY",
                            "currency": "USD",
                            "accession_number": "0001045810-25-000023",
                            "filing_url": "https://www.sec.gov/Archives/example",
                            "revenue": 130497,
                            "gross_profit": 97858,
                            "note": "ignored",
                        }
                    ],
                    "balance_sheets": [
                        {
                            "ticker": "nvda",
                            "report_period": "2025-01-26",
                            "fiscal_period": "FY",
                            "currency": "USD",
                            "total_assets": 111601,
                        }
                    ],
                    "cash_flow_statements": [
                        {
                            "ticker": "nvda",
                            "report_period": "2025-01-26",
                            "fiscal_period": "FY",
                            "currency": "USD",
                            "free_cash_flow": 60853,
                        }
                    ],
                }
            }
        )
    )
    adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=client,
    )

    result = adapter.get_financials(
        ticker="nvda",
        period="annual",
        limit=2,
        report_period_lte="2025-01-26",
    )

    assert result.errors == []
    assert [
        (metric.statement_type, metric.metric_name, metric.value)
        for metric in result.metrics
    ] == [
        ("income_statement", "revenue", 130497.0),
        ("income_statement", "gross_profit", 97858.0),
        ("balance_sheet", "total_assets", 111601.0),
        ("cash_flow_statement", "free_cash_flow", 60853.0),
    ]
    assert result.metrics[0].provider == DataProvider.FINANCIAL_DATASETS
    assert result.metrics[0].source_endpoint == "/financials"
    assert result.metrics[0].ticker == "NVDA"
    assert result.metrics[0].unit == "USD"
    assert result.metrics[0].period == "2025-01-26"
    assert result.metrics[0].fiscal_period == "FY"
    assert result.metrics[0].accession_number == "0001045810-25-000023"
    assert result.metrics[0].source_url == "https://www.sec.gov/Archives/example"
    assert client.calls == [
        {
            "url": "https://api.financialdatasets.ai/financials",
            "params": {
                "ticker": "NVDA",
                "period": "annual",
                "limit": 2,
                "report_period_lte": "2025-01-26",
            },
            "headers": {"X-API-KEY": "secret-key"},
            "timeout": 10.0,
        }
    ]


def test_financial_datasets_kpis_normalize_source_linked_operating_metrics() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "kpi_metrics": [
                    {
                        "ticker": "dal",
                        "metric_name": "load_factor",
                        "value": 82,
                        "unit": "%",
                        "period": "Q4 2025",
                        "period_type": "quarterly",
                        "segment": "Commercial Engines & Services",
                        "yoy_value": 84,
                        "yoy_change_pct": -2.381,
                        "source_text": "Passenger load factor",
                        "source_url": "https://www.sec.gov/Archives/example#:~:text=Passenger",
                    }
                ]
            }
        )
    )
    adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=client,
    )

    result = adapter.get_kpi_metrics(
        ticker="dal",
        metric_name="load_factor",
        period="quarterly",
        limit=4,
    )

    assert result.errors == []
    assert len(result.metrics) == 1
    metric = result.metrics[0]
    assert metric.provider == DataProvider.FINANCIAL_DATASETS
    assert metric.source_endpoint == "/kpi/metrics"
    assert metric.ticker == "DAL"
    assert metric.metric_name == "load_factor"
    assert metric.value == 82.0
    assert metric.unit == "%"
    assert metric.period == "Q4 2025"
    assert metric.period_type == "quarterly"
    assert metric.segment == "Commercial Engines & Services"
    assert metric.yoy_value == 84.0
    assert metric.yoy_change_pct == -2.381
    assert metric.source_text == "Passenger load factor"
    assert metric.source_url == "https://www.sec.gov/Archives/example#:~:text=Passenger"


def test_financial_datasets_filing_items_support_source_text_lookup() -> None:
    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "resource": "AAPL 10-K 2023",
                "ticker": "aapl",
                "cik": "320193",
                "filing_type": "10-K",
                "accession_number": "0000320193-23-000106",
                "year": 2023,
                "items": [
                    {
                        "number": "Item-7",
                        "name": "Management's Discussion and Analysis",
                        "text": "Revenue increased due to services growth.",
                    }
                ],
            }
        )
    )
    adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=client,
    )

    result = adapter.get_filing_items(
        ticker="aapl",
        filing_type="10-K",
        year=2023,
        items=["Item-7"],
    )

    assert result.errors == []
    assert result.items[0].ticker == "AAPL"
    assert result.items[0].cik == "0000320193"
    assert result.items[0].filing_type == "10-K"
    assert result.items[0].accession_number == "0000320193-23-000106"
    assert result.items[0].item_number == "Item-7"
    assert result.items[0].item_name == "Management's Discussion and Analysis"
    assert result.items[0].text == "Revenue increased due to services growth."
    assert result.items[0].provider == DataProvider.FINANCIAL_DATASETS
    assert client.calls[0]["params"] == {
        "ticker": "AAPL",
        "filing_type": "10-K",
        "year": 2023,
        "item": ["Item-7"],
    }


def test_daloopa_requires_customer_documented_endpoint_and_normalizes_configured_payloads() -> None:
    missing_endpoint_adapter = DaloopaFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload={})),
    )
    missing_endpoint = missing_endpoint_adapter.get_kpi_metrics(ticker="NVDA")
    assert missing_endpoint.metrics == []
    assert missing_endpoint.errors[0].error_type == DataProviderErrorType.PROVIDER_UNAVAILABLE

    client = FakeHttpClient(
        FakeHttpResponse(
            payload={
                "kpis": [
                    {
                        "ticker": "nvda",
                        "metric_name": "data_center_revenue",
                        "value": 47500,
                        "unit": "USDm",
                        "period": "Q4 2026",
                        "period_type": "quarterly",
                        "source_text": "Data Center revenue was $47.5 billion.",
                        "source_url": "https://daloopa.example/source",
                    }
                ]
            }
        )
    )
    adapter = DaloopaFundamentalsAdapter(
        api_key="secret-key",
        kpi_endpoint="/customer-docs/kpis",
        http_client=client,
    )

    result = adapter.get_kpi_metrics(ticker="nvda")

    assert result.errors == []
    assert result.metrics[0].provider == DataProvider.DALOOPA
    assert result.metrics[0].source_endpoint == "/customer-docs/kpis"
    assert result.metrics[0].ticker == "NVDA"
    assert result.metrics[0].metric_name == "data_center_revenue"
    assert result.metrics[0].value == 47500.0
    assert result.metrics[0].source_text == "Data Center revenue was $47.5 billion."
    assert client.calls[0]["url"] == "https://api.daloopa.com/customer-docs/kpis"


def test_provider_errors_are_structured_and_journal_safe() -> None:
    missing_key_adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="",
        http_client=FakeHttpClient(FakeHttpResponse(payload={})),
    )
    payment_adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(status_code=402, payload={})),
    )
    retry_adapter = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(
                status_code=503,
                payload={"error": "Filing parse in progress", "secret": "secret-key"},
                headers={"Retry-After": "30"},
            )
        ),
    )
    timeout_adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=FakeHttpClient(TimeoutError("request timed out")),
    )
    malformed_adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=FakeHttpClient(
            FakeHttpResponse(payload=None, json_error=ValueError("bad json"))
        ),
    )
    unsupported_adapter = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=FakeHttpClient(FakeHttpResponse(status_code=404, payload={})),
    )

    assert missing_key_adapter.get_financials(ticker="AAPL").errors[0].error_type == (
        DataProviderErrorType.MISSING_API_KEY
    )
    assert payment_adapter.get_financials(ticker="AAPL").errors[0].error_type == (
        DataProviderErrorType.PAYMENT_REQUIRED
    )
    retry_error = retry_adapter.get_filing_items(
        ticker="AAPL",
        filing_type="10-K",
        year=2024,
    ).errors[0]
    assert retry_error.error_type == DataProviderErrorType.FILING_PARSE_IN_PROGRESS
    assert retry_error.retry_after_seconds == 30
    assert timeout_adapter.get_company_facts(cik="320193").errors[0].error_type == (
        DataProviderErrorType.TIMEOUT
    )
    assert malformed_adapter.get_company_facts(cik="320193").errors[0].error_type == (
        DataProviderErrorType.MALFORMED_RESPONSE
    )
    assert unsupported_adapter.get_company_facts(cik="320193").errors[0].error_type == (
        DataProviderErrorType.UNSUPPORTED_SYMBOL
    )

    serialized = retry_error.model_dump(mode="json")
    rendered = repr(serialized).lower()
    assert "secret-key" not in rendered
    assert "x-api-key" not in rendered
    assert "raw_payload" not in rendered


def test_same_metric_from_multiple_providers_remains_provider_attributed() -> None:
    sec_metric = SecEdgarFundamentalsAdapter(
        user_agent="Prescient pratik@example.com",
        http_client=FakeHttpClient(
            FakeHttpResponse(
                payload={
                    "cik": 1045810,
                    "facts": {
                        "us-gaap": {
                            "Revenues": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "FY",
                                            "end": "2025-01-26",
                                            "val": 130497000000,
                                            "accn": "0001045810-25-000023",
                                        }
                                    ]
                                }
                            }
                        }
                    },
                }
            )
        ),
    ).get_company_facts(cik="1045810", ticker="NVDA").metrics[0]
    fd_metric = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(
            FakeHttpResponse(
                payload={
                    "financials": {
                        "income_statements": [
                            {
                                "ticker": "NVDA",
                                "report_period": "2025-01-26",
                                "currency": "USD",
                                "revenue": 130497,
                            }
                        ]
                    }
                }
            )
        ),
    ).get_financials(ticker="NVDA").metrics[0]

    assert sec_metric.provider == DataProvider.SEC_EDGAR
    assert fd_metric.provider == DataProvider.FINANCIAL_DATASETS
    assert sec_metric.metric_name == "Revenues"
    assert fd_metric.metric_name == "revenue"
    assert sec_metric.model_dump(mode="json") != fd_metric.model_dump(mode="json")


def test_same_fake_r4_5_response_serializes_deterministically() -> None:
    payload = {
        "kpi_metrics": [
            {
                "ticker": "DAL",
                "metric_name": "load_factor",
                "value": 82,
                "unit": "%",
                "period": "Q4 2025",
                "period_type": "quarterly",
            }
        ]
    }
    first = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload=payload)),
    ).get_kpi_metrics(ticker="DAL")
    second = FinancialDatasetsFundamentalsAdapter(
        api_key="secret-key",
        http_client=FakeHttpClient(FakeHttpResponse(payload=payload)),
    ).get_kpi_metrics(ticker="DAL")

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
