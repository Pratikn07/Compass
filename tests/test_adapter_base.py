from vanta.adapters import base


def test_adapter_result_holds_typed_buckets():
    r = base.AdapterResult()
    assert r.news == []
    assert r.filings == []
    assert r.earnings_dates == []
    assert r.estimates == []
    assert r.prices == []


def test_adapter_result_total_counts_all_buckets():
    r = base.AdapterResult(news=[1, 2], prices=[3])  # type: ignore[list-item]
    assert r.total() == 3
