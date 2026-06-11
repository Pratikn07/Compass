from vanta import store
from vanta.models import NewsItem
from datetime import datetime, timezone


class FakeTable:
    def __init__(self, recorder, name):
        self.recorder = recorder
        self.name = name
        self._pending = None

    def upsert(self, rows, on_conflict=None):
        self._pending = ("upsert", rows, on_conflict)
        return self

    def insert(self, rows):
        self._pending = ("insert", rows, None)
        return self

    def execute(self):
        self.recorder.append((self.name, *self._pending))
        return {"data": self._pending[1]}


class FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return FakeTable(self.calls, name)


def test_upsert_news_writes_rows_to_news_table():
    client = FakeClient()
    s = store.Store(client)
    items = [
        NewsItem("MU", "finnhub",
                 datetime(2026, 6, 1, tzinfo=timezone.utc),
                 "h", "http://x", 0.1, {}),
    ]
    n = s.upsert_news(items)
    assert n == 1
    table, op, rows, on_conflict = client.calls[0]
    assert table == "news"
    assert op == "upsert"
    assert on_conflict == "ticker,source,url"
    assert rows[0]["ticker"] == "MU"


def test_upsert_news_empty_is_noop():
    client = FakeClient()
    s = store.Store(client)
    assert s.upsert_news([]) == 0
    assert client.calls == []


def test_log_run_ok_writes_ingest_runs_row():
    client = FakeClient()
    s = store.Store(client)
    s.log_run(source="finnhub", ticker="MU", records=5, status="ok")
    table, op, rows, _ = client.calls[0]
    assert table == "ingest_runs"
    assert op == "insert"
    assert rows[0] == {
        "source": "finnhub", "ticker": "MU",
        "records": 5, "status": "ok", "error": None,
    }


def test_log_run_error_includes_message():
    client = FakeClient()
    s = store.Store(client)
    s.log_run(source="fmp", ticker="WDC", records=0,
              status="error", error="boom")
    _, _, rows, _ = client.calls[0]
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "boom"


def test_seed_tickers_upserts_universe():
    client = FakeClient()
    s = store.Store(client)
    n = s.seed_tickers()
    assert n >= 6
    table, op, rows, on_conflict = client.calls[0]
    assert table == "tickers"
    assert op == "upsert"
    assert on_conflict == "symbol"
    assert any(r["symbol"] == "MU" for r in rows)
