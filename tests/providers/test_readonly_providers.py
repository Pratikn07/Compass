from __future__ import annotations

from compass.providers.daloopa import DaloopaProvider
from compass.providers.financial_datasets import FinancialDatasetsProvider
from compass.providers.finnhub import FinnhubProvider
from compass.providers.fmp import FmpProvider


class Response:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class Client:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


def test_missing_keys_degrade_without_network_requests() -> None:
    client = Client([])

    results = [
        FinnhubProvider(api_key=None, client=client).company_earnings("MU"),
        FmpProvider(api_key=None, client=client).stock_peers("MU"),
        FinancialDatasetsProvider(api_key=None, client=client).financials("MU"),
        DaloopaProvider(api_key=None, endpoint=None, client=client).kpis("MU"),
    ]

    assert client.calls == []
    assert all(result.items == [] for result in results)
    assert all(result.errors[0].error_type == "missing_configuration" for result in results)


def test_finnhub_and_fmp_normalize_read_only_results() -> None:
    finnhub_client = Client([{"symbol": "mu", "actual": 1.2, "estimate": 1.0}])
    fmp_client = Client([{"symbol": "MU", "peersList": ["NVDA", "AMD"]}])

    earnings = FinnhubProvider(api_key="key", client=finnhub_client).company_earnings("mu")
    peers = FmpProvider(api_key="key", client=fmp_client).stock_peers("mu")

    assert earnings.items[0]["ticker"] == "MU"
    assert peers.items[0]["peers"] == ["NVDA", "AMD"]


def test_financial_datasets_and_daloopa_parse_metric_rows() -> None:
    financial_client = Client(
        {"financials": {"income_statements": [{"ticker": "MU", "revenue": 12.5}]}}
    )
    daloopa_client = Client({"kpis": [{"ticker": "MU", "metric_name": "bits", "value": 4}]})

    financials = FinancialDatasetsProvider(
        api_key="key", client=financial_client
    ).financials("MU")
    kpis = DaloopaProvider(
        api_key="key", endpoint="/v1/kpis", client=daloopa_client
    ).kpis("MU")

    assert financials.items[0]["metric_name"] == "revenue"
    assert kpis.items[0]["value"] == 4.0
