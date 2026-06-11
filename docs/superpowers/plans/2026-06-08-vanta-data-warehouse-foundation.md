# Vanta Data Warehouse Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Supabase Postgres warehouse and a free-tier ingestion pipeline that fills it with news, filings, earnings dates, estimates, and prices for MU + its competitive space (WDC, SNDK, NVDA, AMD, AVGO), with point-in-time provenance on every row.

**Architecture:** Python package `vanta/` with one swappable adapter per data source (Finnhub, Alpha Vantage, FMP, SEC EDGAR), a thin Supabase store layer (PostgREST via supabase-py), and an orchestrator (`run.py`) that loops tickers × adapters, writes rows, logs each attempt to `ingest_runs`, and prints a coverage report. Schema is managed as version-controlled SQL migrations applied via the Supabase CLI.

**Tech Stack:** Python 3.14, `uv` (env + deps), `supabase` (PostgREST client — pure Python, no compiled deps), `requests`, `python-dotenv`, `pytest` + `responses` (HTTP mocking). Supabase CLI for migrations.

**Supabase project:** `vanta` (ref `thltgeykhktvawwyhvif`, org `vanta`, us-east-1). Credentials already in gitignored `.env`.

---

## File Structure

```
vanta/
  pyproject.toml              # uv project, deps, pytest config
  .env                        # EXISTS (gitignored) — keys + Supabase creds
  vanta/
    __init__.py
    config.py                 # ticker universe, theme map, peer edges, env loading
    models.py                 # normalized record dataclasses (NewsItem, Filing, ...)
    store.py                  # Supabase client + typed upsert helpers + ingest_runs logging
    adapters/
      __init__.py
      base.py                 # Adapter protocol: fetch(ticker) -> list[record]
      finnhub.py              # company news, earnings dates, estimates+surprise
      alphavantage.py         # news + sentiment
      fmp.py                  # peers, daily prices, press releases
      sec.py                  # SEC EDGAR recent 8-K filings
    run.py                    # orchestrator + coverage report
  supabase/
    migrations/
      0001_initial_schema.sql # tables: tickers, news, filings, earnings_dates, estimates, prices, ingest_runs
  tests/
    __init__.py
    fixtures/                 # saved JSON API responses
    test_config.py
    test_store.py
    test_finnhub.py
    test_alphavantage.py
    test_fmp.py
    test_sec.py
    test_run.py
```

**Responsibility boundaries:**
- `config.py` — *what* we pull (tickers/themes) + env access. No I/O to APIs.
- `models.py` — the normalized shapes every adapter must return. Pure data.
- `adapters/*` — *how* to get raw data from one source and normalize it. One source = one file. No DB writes.
- `store.py` — *where* data lands. Only file that talks to Supabase.
- `run.py` — *orchestration*. Wires adapters → store, handles per-source failure, prints report.

---

## Task 1: Project scaffold + dependencies

**Files:**
- Create: `vanta/pyproject.toml`
- Create: `vanta/vanta/__init__.py`
- Create: `vanta/tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "vanta"
version = "0.1.0"
description = "Earnings options intelligence — data warehouse foundation"
requires-python = ">=3.12"
dependencies = [
    "supabase>=2.9.0",
    "requests>=2.32.0",
    "python-dotenv>=1.0.1",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "responses>=0.25.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create empty package markers**

`vanta/vanta/__init__.py`:
```python
"""Vanta — earnings options intelligence."""
```

`vanta/tests/__init__.py`:
```python
```

- [ ] **Step 3: Install deps with uv**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv sync`
Expected: creates `.venv`, resolves and installs supabase, requests, python-dotenv, pytest, responses. Ends with "Installed N packages".

- [ ] **Step 4: Verify pytest runs (no tests yet)**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest`
Expected: exit 0 with "no tests ran" (collected 0 items).

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add pyproject.toml uv.lock vanta/__init__.py tests/__init__.py
git commit -m "chore: scaffold vanta python project with uv

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Config — ticker universe + env loading

**Files:**
- Create: `vanta/vanta/config.py`
- Test: `vanta/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_config.py`:
```python
from vanta import config


def test_universe_contains_target_and_peers():
    symbols = {t.symbol for t in config.UNIVERSE}
    assert "MU" in symbols
    assert {"WDC", "SNDK", "NVDA", "AMD", "AVGO"} <= symbols


def test_target_ticker_is_mu():
    assert config.TARGET == "MU"


def test_each_ticker_has_theme_and_role():
    for t in config.UNIVERSE:
        assert t.symbol
        assert t.theme == "AI Memory"
        assert t.role in {"target", "rival", "demand_driver"}


def test_mu_role_is_target():
    mu = next(t for t in config.UNIVERSE if t.symbol == "MU")
    assert mu.role == "target"


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "abc123")
    assert config.require_env("FINNHUB_API_KEY") == "abc123"


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="MISSING_KEY"):
        config.require_env("MISSING_KEY")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError` or `AttributeError: module 'vanta.config' has no attribute 'UNIVERSE'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/config.py`:
```python
"""Ticker universe, theme map, and environment access for vanta."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # loads .env at repo root if present

TARGET = "MU"


@dataclass(frozen=True)
class Ticker:
    symbol: str
    name: str
    theme: str
    role: str  # "target" | "rival" | "demand_driver"


UNIVERSE: list[Ticker] = [
    Ticker("MU", "Micron Technology", "AI Memory", "target"),
    Ticker("WDC", "Western Digital", "AI Memory", "rival"),
    Ticker("SNDK", "SanDisk", "AI Memory", "rival"),
    Ticker("NVDA", "NVIDIA", "AI Memory", "demand_driver"),
    Ticker("AMD", "Advanced Micro Devices", "AI Memory", "demand_driver"),
    Ticker("AVGO", "Broadcom", "AI Memory", "demand_driver"),
]


def require_env(name: str) -> str:
    """Return env var or raise a clear error naming the missing var."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_config.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/config.py tests/test_config.py
git commit -m "feat: ticker universe + env config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Normalized record models

**Files:**
- Create: `vanta/vanta/models.py`
- Test: `vanta/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_models.py`:
```python
from datetime import date, datetime, timezone

from vanta import models


def test_news_item_to_row_includes_ticker_and_published():
    item = models.NewsItem(
        ticker="MU",
        source="finnhub",
        published_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        headline="Micron beats",
        url="http://example.com/a",
        sentiment=0.5,
        raw={"id": 1},
    )
    row = item.to_row()
    assert row["ticker"] == "MU"
    assert row["source"] == "finnhub"
    assert row["headline"] == "Micron beats"
    assert row["sentiment"] == 0.5
    assert row["url"] == "http://example.com/a"
    assert "published_at" in row
    assert row["raw"] == {"id": 1}


def test_price_bar_to_row():
    bar = models.PriceBar(
        ticker="MU", d=date(2026, 6, 1),
        open=100.0, high=105.0, low=99.0, close=104.0, volume=1000,
    )
    row = bar.to_row()
    assert row["ticker"] == "MU"
    assert row["date"] == "2026-06-01"
    assert row["close"] == 104.0
    assert row["volume"] == 1000


def test_filing_to_row():
    f = models.Filing(
        ticker="MU", form_type="8-K",
        filed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        url="http://sec.gov/x", raw={"accn": "1"},
    )
    row = f.to_row()
    assert row["ticker"] == "MU"
    assert row["form_type"] == "8-K"
    assert row["url"] == "http://sec.gov/x"


def test_earnings_date_to_row():
    e = models.EarningsDate(
        ticker="MU", report_date=date(2026, 6, 24), confirmed=True,
    )
    row = e.to_row()
    assert row["ticker"] == "MU"
    assert row["report_date"] == "2026-06-24"
    assert row["confirmed"] is True


def test_estimate_to_row():
    est = models.Estimate(
        ticker="MU", period="2026Q3", eps_est=1.5, rev_est=8.0e9,
        eps_actual=None, surprise_pct=None, as_of=date(2026, 6, 1),
    )
    row = est.to_row()
    assert row["ticker"] == "MU"
    assert row["period"] == "2026Q3"
    assert row["eps_est"] == 1.5
    assert row["as_of"] == "2026-06-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vanta.models'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/models.py`:
```python
"""Normalized record types returned by adapters and written by the store.

Every fact-bearing row is enriched with `ingested_at` at write time in the
store layer (point-in-time provenance), so models intentionally do NOT set it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class NewsItem:
    ticker: str
    source: str
    published_at: datetime
    headline: str
    url: str
    sentiment: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "headline": self.headline,
            "url": self.url,
            "sentiment": self.sentiment,
            "raw": self.raw,
        }


@dataclass
class Filing:
    ticker: str
    form_type: str
    filed_at: datetime
    url: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "form_type": self.form_type,
            "filed_at": self.filed_at.isoformat(),
            "url": self.url,
            "raw": self.raw,
        }


@dataclass
class EarningsDate:
    ticker: str
    report_date: date
    confirmed: bool

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_date": self.report_date.isoformat(),
            "confirmed": self.confirmed,
        }


@dataclass
class Estimate:
    ticker: str
    period: str
    eps_est: float | None
    rev_est: float | None
    eps_actual: float | None
    surprise_pct: float | None
    as_of: date

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "period": self.period,
            "eps_est": self.eps_est,
            "rev_est": self.rev_est,
            "eps_actual": self.eps_actual,
            "surprise_pct": self.surprise_pct,
            "as_of": self.as_of.isoformat(),
        }


@dataclass
class PriceBar:
    ticker: str
    d: date
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "date": self.d.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_models.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/models.py tests/test_models.py
git commit -m "feat: normalized record models

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Database schema migration

**Files:**
- Create: `vanta/supabase/migrations/0001_initial_schema.sql`

- [ ] **Step 1: Write the migration SQL**

`vanta/supabase/migrations/0001_initial_schema.sql`:
```sql
-- Vanta warehouse — Step 1 schema.
-- Every fact table carries ingested_at (when WE learned it) for point-in-time correctness.

create table if not exists tickers (
    symbol        text primary key,
    name          text not null,
    theme         text not null,
    role          text not null,
    peer_symbols  text[] not null default '{}',
    inserted_at   timestamptz not null default now()
);

create table if not exists news (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    source        text not null,
    published_at  timestamptz,
    ingested_at   timestamptz not null default now(),
    headline      text not null,
    url           text not null,
    sentiment     double precision,
    raw           jsonb not null default '{}',
    unique (ticker, source, url)
);

create table if not exists filings (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    form_type     text not null,
    filed_at      timestamptz,
    ingested_at   timestamptz not null default now(),
    url           text not null,
    raw           jsonb not null default '{}',
    unique (ticker, url)
);

create table if not exists earnings_dates (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    report_date   date not null,
    confirmed     boolean not null default false,
    ingested_at   timestamptz not null default now(),
    unique (ticker, report_date)
);

create table if not exists estimates (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    period        text not null,
    eps_est       double precision,
    rev_est       double precision,
    eps_actual    double precision,
    surprise_pct  double precision,
    as_of         date not null,
    ingested_at   timestamptz not null default now(),
    unique (ticker, period, as_of)
);

create table if not exists prices (
    id            bigint generated always as identity primary key,
    ticker        text not null references tickers(symbol),
    date          date not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    volume        bigint,
    ingested_at   timestamptz not null default now(),
    unique (ticker, date)
);

create table if not exists ingest_runs (
    id            bigint generated always as identity primary key,
    started_at    timestamptz not null default now(),
    source        text not null,
    ticker        text not null,
    records       integer not null default 0,
    status        text not null,          -- 'ok' | 'error'
    error         text
);
```

- [ ] **Step 2: Link the Supabase project**

Run:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
export SUPABASE_DB_PASSWORD=$(grep -oE 'SUPABASE_DB_PASSWORD=.*' .secrets/db_password.env | cut -d= -f2-)
supabase link --project-ref thltgeykhktvawwyhvif --password "$SUPABASE_DB_PASSWORD"
```
Expected: "Finished supabase link." Creates/updates `supabase/config.toml`.

- [ ] **Step 3: Push the migration**

Run:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
supabase db push --password "$SUPABASE_DB_PASSWORD"
```
Expected: lists `0001_initial_schema.sql` as applied; "Finished supabase db push."

- [ ] **Step 4: Verify tables exist**

Run:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
supabase db dump --schema public --password "$SUPABASE_DB_PASSWORD" -f /tmp/vanta_schema_check.sql
grep -E "CREATE TABLE" /tmp/vanta_schema_check.sql
```
Expected: lines for tickers, news, filings, earnings_dates, estimates, prices, ingest_runs.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add supabase/migrations/0001_initial_schema.sql supabase/config.toml
git commit -m "feat: initial warehouse schema with point-in-time ingested_at

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Store layer (Supabase writes + ingest_runs)

**Files:**
- Create: `vanta/vanta/store.py`
- Test: `vanta/tests/test_store.py`

The store uses supabase-py. Tests inject a fake client so no network is needed.

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_store.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vanta.store'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/store.py`:
```python
"""Supabase store layer — the only module that writes to the warehouse.

Tables enforce uniqueness, so we upsert (idempotent re-runs). `ingested_at`
is set by the database default, preserving point-in-time provenance.
"""
from __future__ import annotations

from typing import Any

from . import config
from .models import EarningsDate, Estimate, Filing, NewsItem, PriceBar


def make_client():
    """Build a Supabase client from env (service role key for writes)."""
    from supabase import create_client

    url = config.require_env("SUPABASE_URL")
    key = config.require_env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


class Store:
    def __init__(self, client):
        self.client = client

    def _upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
        if not rows:
            return 0
        self.client.table(table).upsert(rows, on_conflict=on_conflict).execute()
        return len(rows)

    def seed_tickers(self) -> int:
        rows = [
            {
                "symbol": t.symbol, "name": t.name,
                "theme": t.theme, "role": t.role,
            }
            for t in config.UNIVERSE
        ]
        return self._upsert("tickers", rows, "symbol")

    def upsert_news(self, items: list[NewsItem]) -> int:
        return self._upsert("news", [i.to_row() for i in items], "ticker,source,url")

    def upsert_filings(self, items: list[Filing]) -> int:
        return self._upsert("filings", [i.to_row() for i in items], "ticker,url")

    def upsert_earnings_dates(self, items: list[EarningsDate]) -> int:
        return self._upsert(
            "earnings_dates", [i.to_row() for i in items], "ticker,report_date"
        )

    def upsert_estimates(self, items: list[Estimate]) -> int:
        return self._upsert(
            "estimates", [i.to_row() for i in items], "ticker,period,as_of"
        )

    def upsert_prices(self, items: list[PriceBar]) -> int:
        return self._upsert("prices", [i.to_row() for i in items], "ticker,date")

    def log_run(self, *, source: str, ticker: str, records: int,
                status: str, error: str | None = None) -> None:
        self.client.table("ingest_runs").insert([{
            "source": source, "ticker": ticker,
            "records": records, "status": status, "error": error,
        }]).execute()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_store.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/store.py tests/test_store.py
git commit -m "feat: supabase store layer with idempotent upserts + run logging

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Adapter base protocol

**Files:**
- Create: `vanta/vanta/adapters/__init__.py`
- Create: `vanta/vanta/adapters/base.py`
- Test: `vanta/tests/test_adapter_base.py`

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_adapter_base.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_adapter_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vanta.adapters'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/adapters/__init__.py`:
```python
"""Data source adapters. One module per source; each returns an AdapterResult."""
```

`vanta/vanta/adapters/base.py`:
```python
"""Adapter contract. Each adapter fetches one source for one ticker and returns
normalized records grouped into an AdapterResult. Adapters never touch the DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import EarningsDate, Estimate, Filing, NewsItem, PriceBar


@dataclass
class AdapterResult:
    news: list[NewsItem] = field(default_factory=list)
    filings: list[Filing] = field(default_factory=list)
    earnings_dates: list[EarningsDate] = field(default_factory=list)
    estimates: list[Estimate] = field(default_factory=list)
    prices: list[PriceBar] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.news) + len(self.filings) + len(self.earnings_dates)
            + len(self.estimates) + len(self.prices)
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_adapter_base.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/adapters/__init__.py vanta/adapters/base.py tests/test_adapter_base.py
git commit -m "feat: adapter base protocol (AdapterResult)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Finnhub adapter (news, earnings dates, estimates)

**Files:**
- Create: `vanta/vanta/adapters/finnhub.py`
- Test: `vanta/tests/test_finnhub.py`

Endpoints used (free tier): `/company-news`, `/calendar/earnings`. Uses `responses` to mock HTTP.

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_finnhub.py`:
```python
import responses

from vanta.adapters import finnhub


@responses.activate
def test_fetch_returns_news_and_earnings(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://finnhub.io/api/v1/company-news",
        json=[{
            "datetime": 1748779200,  # 2025-06-01 UTC
            "headline": "Micron news",
            "url": "http://finnhub/news/1",
            "summary": "x",
        }],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://finnhub.io/api/v1/calendar/earnings",
        json={"earningsCalendar": [
            {"symbol": "MU", "date": "2026-06-24",
             "epsEstimate": 1.5, "revenueEstimate": 8000000000,
             "epsActual": None, "quarter": 3, "year": 2026},
        ]},
        status=200,
    )

    result = finnhub.fetch("MU", days=30)

    assert len(result.news) == 1
    assert result.news[0].ticker == "MU"
    assert result.news[0].source == "finnhub"
    assert result.news[0].url == "http://finnhub/news/1"

    assert len(result.earnings_dates) == 1
    assert result.earnings_dates[0].report_date.isoformat() == "2026-06-24"

    assert len(result.estimates) == 1
    assert result.estimates[0].eps_est == 1.5
    assert result.estimates[0].period == "2026Q3"


@responses.activate
def test_fetch_handles_empty_news(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test")
    responses.add(responses.GET,
                  "https://finnhub.io/api/v1/company-news",
                  json=[], status=200)
    responses.add(responses.GET,
                  "https://finnhub.io/api/v1/calendar/earnings",
                  json={"earningsCalendar": []}, status=200)
    result = finnhub.fetch("MU", days=30)
    assert result.news == []
    assert result.earnings_dates == []
    assert result.estimates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_finnhub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vanta.adapters.finnhub'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/adapters/finnhub.py`:
```python
"""Finnhub adapter: company news, earnings calendar dates, and estimates."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import requests

from .. import config
from ..models import EarningsDate, Estimate, NewsItem
from .base import AdapterResult

BASE = "https://finnhub.io/api/v1"
TIMEOUT = 30


def _quarter_label(item: dict) -> str:
    year = item.get("year")
    quarter = item.get("quarter")
    if year and quarter:
        return f"{year}Q{quarter}"
    return item.get("date", "unknown")


def fetch(ticker: str, days: int = 30) -> AdapterResult:
    key = config.require_env("FINNHUB_API_KEY")
    result = AdapterResult()
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=days)).isoformat()
    to = today.isoformat()

    # Company news
    resp = requests.get(
        f"{BASE}/company-news",
        params={"symbol": ticker, "from": frm, "to": to, "token": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for art in resp.json() or []:
        ts = art.get("datetime")
        published = (
            datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        )
        if not art.get("url"):
            continue
        result.news.append(NewsItem(
            ticker=ticker,
            source="finnhub",
            published_at=published or datetime.now(timezone.utc),
            headline=art.get("headline", ""),
            url=art["url"],
            sentiment=None,
            raw=art,
        ))

    # Earnings calendar (dates + estimates)
    resp = requests.get(
        f"{BASE}/calendar/earnings",
        params={"symbol": ticker, "from": frm,
                "to": (today + timedelta(days=60)).isoformat(), "token": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for item in (resp.json() or {}).get("earningsCalendar", []):
        d = item.get("date")
        if d:
            result.earnings_dates.append(EarningsDate(
                ticker=ticker,
                report_date=date.fromisoformat(d),
                confirmed=item.get("epsActual") is not None,
            ))
            result.estimates.append(Estimate(
                ticker=ticker,
                period=_quarter_label(item),
                eps_est=item.get("epsEstimate"),
                rev_est=item.get("revenueEstimate"),
                eps_actual=item.get("epsActual"),
                surprise_pct=None,
                as_of=today,
            ))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_finnhub.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/adapters/finnhub.py tests/test_finnhub.py
git commit -m "feat: finnhub adapter (news, earnings dates, estimates)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Alpha Vantage adapter (news + sentiment)

**Files:**
- Create: `vanta/vanta/adapters/alphavantage.py`
- Test: `vanta/tests/test_alphavantage.py`

Endpoint: `NEWS_SENTIMENT`. Returns `feed[]` with `overall_sentiment_score` and per-ticker sentiment in `ticker_sentiment[]`.

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_alphavantage.py`:
```python
import responses

from vanta.adapters import alphavantage


@responses.activate
def test_fetch_returns_news_with_ticker_sentiment(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://www.alphavantage.co/query",
        json={"feed": [{
            "title": "Micron AI demand",
            "url": "http://av/news/1",
            "time_published": "20260601T120000",
            "overall_sentiment_score": 0.3,
            "ticker_sentiment": [
                {"ticker": "MU", "ticker_sentiment_score": "0.45"},
                {"ticker": "NVDA", "ticker_sentiment_score": "0.10"},
            ],
        }]},
        status=200,
    )
    result = alphavantage.fetch("MU")
    assert len(result.news) == 1
    item = result.news[0]
    assert item.ticker == "MU"
    assert item.source == "alphavantage"
    assert item.url == "http://av/news/1"
    assert item.sentiment == 0.45  # per-ticker score preferred over overall


@responses.activate
def test_fetch_handles_rate_limit_note(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://www.alphavantage.co/query",
        json={"Note": "rate limited"},
        status=200,
    )
    result = alphavantage.fetch("MU")
    assert result.news == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_alphavantage.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/adapters/alphavantage.py`:
```python
"""Alpha Vantage adapter: news articles with sentiment scoring."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from .. import config
from ..models import NewsItem
from .base import AdapterResult

BASE = "https://www.alphavantage.co/query"
TIMEOUT = 30


def _parse_time(value: str) -> datetime:
    # Alpha Vantage format: 20260601T120000
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _ticker_sentiment(article: dict, ticker: str) -> float | None:
    for ts in article.get("ticker_sentiment", []):
        if ts.get("ticker") == ticker:
            try:
                return float(ts.get("ticker_sentiment_score"))
            except (ValueError, TypeError):
                return None
    score = article.get("overall_sentiment_score")
    try:
        return float(score) if score is not None else None
    except (ValueError, TypeError):
        return None


def fetch(ticker: str) -> AdapterResult:
    key = config.require_env("ALPHAVANTAGE_API_KEY")
    result = AdapterResult()
    resp = requests.get(
        BASE,
        params={"function": "NEWS_SENTIMENT", "tickers": ticker,
                "limit": 50, "apikey": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    # Free tier returns {"Note": ...} or {"Information": ...} when throttled.
    feed = payload.get("feed")
    if not feed:
        return result
    for art in feed:
        if not art.get("url"):
            continue
        result.news.append(NewsItem(
            ticker=ticker,
            source="alphavantage",
            published_at=_parse_time(art.get("time_published", "")),
            headline=art.get("title", ""),
            url=art["url"],
            sentiment=_ticker_sentiment(art, ticker),
            raw=art,
        ))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_alphavantage.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/adapters/alphavantage.py tests/test_alphavantage.py
git commit -m "feat: alpha vantage adapter (news + sentiment)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: FMP adapter (peers, prices, press releases)

**Files:**
- Create: `vanta/vanta/adapters/fmp.py`
- Test: `vanta/tests/test_fmp.py`

Endpoints (free tier): `/v3/historical-price-full/{ticker}` (prices), `/v4/stock_peers` (peers), `/v3/press-releases/{ticker}` (news). FMP peers populate the `tickers.peer_symbols` column via a dedicated function.

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_fmp.py`:
```python
import responses

from vanta.adapters import fmp


@responses.activate
def test_fetch_returns_prices_and_press_releases(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://financialmodelingprep.com/api/v3/historical-price-full/MU",
        json={"historical": [
            {"date": "2026-06-01", "open": 100, "high": 105,
             "low": 99, "close": 104, "volume": 1000},
        ]},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://financialmodelingprep.com/api/v3/press-releases/MU",
        json=[{"date": "2026-06-01 12:00:00", "title": "MU PR",
               "text": "body"}],
        status=200,
    )
    result = fmp.fetch("MU", price_days=5)
    assert len(result.prices) == 1
    assert result.prices[0].close == 104
    assert len(result.news) == 1
    assert result.news[0].source == "fmp"
    assert result.news[0].headline == "MU PR"


@responses.activate
def test_fetch_peers_returns_peer_symbols(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://financialmodelingprep.com/api/v4/stock_peers",
        json=[{"symbol": "MU", "peersList": ["WDC", "STX", "NVDA"]}],
        status=200,
    )
    peers = fmp.fetch_peers("MU")
    assert peers == ["WDC", "STX", "NVDA"]


@responses.activate
def test_fetch_handles_missing_historical(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test")
    responses.add(
        responses.GET,
        "https://financialmodelingprep.com/api/v3/historical-price-full/MU",
        json={}, status=200,
    )
    responses.add(
        responses.GET,
        "https://financialmodelingprep.com/api/v3/press-releases/MU",
        json=[], status=200,
    )
    result = fmp.fetch("MU", price_days=5)
    assert result.prices == []
    assert result.news == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_fmp.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/adapters/fmp.py`:
```python
"""FMP adapter: daily prices, press releases (news), and peer discovery."""
from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from .. import config
from ..models import NewsItem, PriceBar
from .base import AdapterResult

BASE = "https://financialmodelingprep.com/api"
TIMEOUT = 30


def _parse_pr_time(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def fetch(ticker: str, price_days: int = 120) -> AdapterResult:
    key = config.require_env("FMP_API_KEY")
    result = AdapterResult()

    # Prices
    resp = requests.get(
        f"{BASE}/v3/historical-price-full/{ticker}",
        params={"timeseries": price_days, "apikey": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for bar in (resp.json() or {}).get("historical", []):
        result.prices.append(PriceBar(
            ticker=ticker,
            d=date.fromisoformat(bar["date"]),
            open=bar.get("open"),
            high=bar.get("high"),
            low=bar.get("low"),
            close=bar.get("close"),
            volume=int(bar.get("volume") or 0),
        ))

    # Press releases as news
    resp = requests.get(
        f"{BASE}/v3/press-releases/{ticker}",
        params={"apikey": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    for pr in resp.json() or []:
        title = pr.get("title", "")
        url = pr.get("url") or f"fmp-pr://{ticker}/{pr.get('date', '')}"
        result.news.append(NewsItem(
            ticker=ticker,
            source="fmp",
            published_at=_parse_pr_time(pr.get("date", "")),
            headline=title,
            url=url,
            sentiment=None,
            raw=pr,
        ))
    return result


def fetch_peers(ticker: str) -> list[str]:
    """Return FMP's peer list for a ticker (for the tickers.peer_symbols column)."""
    key = config.require_env("FMP_API_KEY")
    resp = requests.get(
        f"{BASE}/v4/stock_peers",
        params={"symbol": ticker, "apikey": key},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json() or []
    if data and isinstance(data, list):
        return data[0].get("peersList", [])
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_fmp.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/adapters/fmp.py tests/test_fmp.py
git commit -m "feat: fmp adapter (prices, press releases, peers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: SEC EDGAR adapter (8-K filings)

**Files:**
- Create: `vanta/vanta/adapters/sec.py`
- Test: `vanta/tests/test_sec.py`

SEC EDGAR needs a ticker→CIK map (`https://www.sec.gov/files/company_tickers.json`) then `https://data.sec.gov/submissions/CIK##########.json`. Requires a descriptive `User-Agent` (from `SEC_USER_AGENT`).

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_sec.py`:
```python
import responses

from vanta.adapters import sec


@responses.activate
def test_fetch_returns_8k_filings(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "vanta test@example.com")
    responses.add(
        responses.GET,
        "https://www.sec.gov/files/company_tickers.json",
        json={"0": {"cik_str": 723125, "ticker": "MU",
                    "title": "MICRON TECHNOLOGY INC"}},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0000723125.json",
        json={"filings": {"recent": {
            "form": ["8-K", "10-Q"],
            "filingDate": ["2026-06-02", "2026-04-01"],
            "accessionNumber": ["0000723125-26-000045", "0000723125-26-000030"],
            "primaryDocument": ["mu8k.htm", "mu10q.htm"],
        }}},
        status=200,
    )
    result = sec.fetch("MU")
    assert len(result.filings) == 1  # only the 8-K
    f = result.filings[0]
    assert f.ticker == "MU"
    assert f.form_type == "8-K"
    assert "723125" in f.url
    assert f.filed_at.date().isoformat() == "2026-06-02"


@responses.activate
def test_fetch_unknown_ticker_returns_empty(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "vanta test@example.com")
    responses.add(
        responses.GET,
        "https://www.sec.gov/files/company_tickers.json",
        json={"0": {"cik_str": 1, "ticker": "AAA", "title": "X"}},
        status=200,
    )
    result = sec.fetch("ZZZZ")
    assert result.filings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_sec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/adapters/sec.py`:
```python
"""SEC EDGAR adapter: recent 8-K filings (material events / 'deals')."""
from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from .. import config
from ..models import Filing
from .base import AdapterResult

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
TIMEOUT = 30


def _headers() -> dict[str, str]:
    return {"User-Agent": config.require_env("SEC_USER_AGENT")}


def _cik_for(ticker: str) -> int | None:
    resp = requests.get(TICKERS_URL, headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    for entry in (resp.json() or {}).values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return int(entry["cik_str"])
    return None


def fetch(ticker: str, form_types: tuple[str, ...] = ("8-K",)) -> AdapterResult:
    result = AdapterResult()
    cik = _cik_for(ticker)
    if cik is None:
        return result

    resp = requests.get(
        SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=TIMEOUT
    )
    resp.raise_for_status()
    recent = (resp.json() or {}).get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    for form, filed, accn, doc in zip(forms, dates, accns, docs):
        if form not in form_types:
            continue
        accn_nodash = accn.replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accn_nodash}/{doc}"
        )
        try:
            filed_at = datetime.combine(
                date.fromisoformat(filed),
                datetime.min.time(), tzinfo=timezone.utc,
            )
        except ValueError:
            filed_at = datetime.now(timezone.utc)
        result.filings.append(Filing(
            ticker=ticker,
            form_type=form,
            filed_at=filed_at,
            url=url,
            raw={"accessionNumber": accn, "cik": cik},
        ))
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_sec.py -v`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/adapters/sec.py tests/test_sec.py
git commit -m "feat: sec edgar adapter (8-K filings)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Orchestrator + coverage report

**Files:**
- Create: `vanta/vanta/run.py`
- Test: `vanta/tests/test_run.py`

`run.py` loops the universe × adapters, writes via the store, logs every attempt to `ingest_runs` (per-source try/except so one failure never aborts the run), and prints a coverage report. Tests use fakes — no network, no DB.

- [ ] **Step 1: Write the failing test**

`vanta/tests/test_run.py`:
```python
from datetime import datetime, timezone

from vanta import run
from vanta.adapters.base import AdapterResult
from vanta.models import NewsItem


class RecordingStore:
    def __init__(self):
        self.news = 0
        self.runs = []

    def seed_tickers(self):
        return 6

    def upsert_news(self, items):
        self.news += len(items)
        return len(items)

    def upsert_filings(self, items):
        return len(items)

    def upsert_earnings_dates(self, items):
        return len(items)

    def upsert_estimates(self, items):
        return len(items)

    def upsert_prices(self, items):
        return len(items)

    def log_run(self, *, source, ticker, records, status, error=None):
        self.runs.append((source, ticker, status, records, error))


def _ok_adapter(ticker):
    return AdapterResult(news=[
        NewsItem(ticker, "fake", datetime.now(timezone.utc),
                 "h", f"http://x/{ticker}", None, {}),
    ])


def _boom_adapter(ticker):
    raise RuntimeError("api down")


def test_ingest_writes_and_logs_ok():
    store = RecordingStore()
    report = run.ingest(
        store=store,
        tickers=["MU", "NVDA"],
        adapters={"fake": _ok_adapter},
    )
    assert store.news == 2
    assert all(r[2] == "ok" for r in store.runs)
    assert report["MU"]["fake"]["status"] == "ok"
    assert report["MU"]["fake"]["records"] == 1


def test_ingest_isolates_adapter_failure():
    store = RecordingStore()
    report = run.ingest(
        store=store,
        tickers=["MU"],
        adapters={"fake": _ok_adapter, "boom": _boom_adapter},
    )
    # ok adapter still ran and wrote
    assert store.news == 1
    # failure logged, not raised
    statuses = {(r[0], r[2]) for r in store.runs}
    assert ("fake", "ok") in statuses
    assert ("boom", "error") in statuses
    assert report["MU"]["boom"]["status"] == "error"


def test_format_report_marks_gaps():
    report = {
        "MU": {"fake": {"status": "ok", "records": 3}},
        "SNDK": {"fake": {"status": "ok", "records": 0}},
    }
    text = run.format_report(report)
    assert "MU" in text
    assert "SNDK" in text
    assert "⚠" in text  # zero-record source flagged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vanta.run'`.

- [ ] **Step 3: Write minimal implementation**

`vanta/vanta/run.py`:
```python
"""Orchestrator: loop tickers x adapters, write to warehouse, log + report.

Each (ticker, source) is isolated: a failing source logs an error row and the
run continues. An adapter is any callable `fetch(ticker) -> AdapterResult`.
"""
from __future__ import annotations

import time
from typing import Callable

from . import config
from .adapters import alphavantage, finnhub, fmp, sec
from .adapters.base import AdapterResult
from .store import Store, make_client

Adapter = Callable[[str], AdapterResult]

DEFAULT_ADAPTERS: dict[str, Adapter] = {
    "finnhub": finnhub.fetch,
    "alphavantage": alphavantage.fetch,
    "fmp": fmp.fetch,
    "sec": sec.fetch,
}


def _write(store, result: AdapterResult) -> int:
    return (
        store.upsert_news(result.news)
        + store.upsert_filings(result.filings)
        + store.upsert_earnings_dates(result.earnings_dates)
        + store.upsert_estimates(result.estimates)
        + store.upsert_prices(result.prices)
    )


def ingest(*, store, tickers: list[str], adapters: dict[str, Adapter],
           throttle: float = 0.0) -> dict:
    """Run every adapter for every ticker. Returns a coverage report dict."""
    store.seed_tickers()
    report: dict[str, dict] = {t: {} for t in tickers}
    for ticker in tickers:
        for name, fetch in adapters.items():
            try:
                result = fetch(ticker)
                records = _write(store, result)
                store.log_run(source=name, ticker=ticker,
                              records=records, status="ok")
                report[ticker][name] = {"status": "ok", "records": records}
            except Exception as exc:  # isolate per-source failure
                store.log_run(source=name, ticker=ticker, records=0,
                              status="error", error=str(exc))
                report[ticker][name] = {"status": "error", "error": str(exc)}
            if throttle:
                time.sleep(throttle)
    return report


def format_report(report: dict) -> str:
    lines = ["", "=== Vanta ingestion coverage ==="]
    for ticker, sources in report.items():
        lines.append(f"\n{ticker}:")
        for name, info in sources.items():
            if info["status"] == "error":
                lines.append(f"  ⚠ {name}: ERROR — {info.get('error')}")
            elif info.get("records", 0) == 0:
                lines.append(f"  ⚠ {name}: 0 records (gap)")
            else:
                lines.append(f"  ✓ {name}: {info['records']} records")
    return "\n".join(lines)


def main() -> None:
    store = Store(make_client())
    tickers = [t.symbol for t in config.UNIVERSE]
    report = ingest(
        store=store, tickers=tickers,
        adapters=DEFAULT_ADAPTERS, throttle=1.0,
    )
    print(format_report(report))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest tests/test_run.py -v`
Expected: PASS — 3 passed.

- [ ] **Step 5: Run the full test suite**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run pytest`
Expected: all tests pass (config, models, store, adapter_base, finnhub, alphavantage, fmp, sec, run).

- [ ] **Step 6: Commit**

```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add vanta/run.py tests/test_run.py
git commit -m "feat: orchestrator + coverage report with per-source failure isolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Live end-to-end run against the real warehouse

This is the manual validation gate — real APIs, real Supabase. Run after all unit tests pass.

- [ ] **Step 1: Confirm migration is applied** (depends on Task 4)

Run:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
export SUPABASE_DB_PASSWORD=$(grep -oE 'SUPABASE_DB_PASSWORD=.*' .secrets/db_password.env | cut -d= -f2-)
supabase migration list --password "$SUPABASE_DB_PASSWORD"
```
Expected: `0001_initial_schema` shown as applied (Local + Remote).

- [ ] **Step 2: Run the live ingestion**

Run: `cd /Users/pratik.nandoskar/Documents/working/vanta && uv run python -m vanta.run`
Expected: a coverage report prints. Some sources may show `⚠ 0 records` or rate-limit gaps (Alpha Vantage free tier is ~25 req/day) — that is acceptable and is the honest signal we're capturing. No uncaught exception; the run completes.

- [ ] **Step 3: Verify rows landed in Supabase**

Run (counts via PostgREST + service key):
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
uv run python -c "
from vanta.store import make_client
c = make_client()
for t in ['tickers','news','filings','earnings_dates','estimates','prices','ingest_runs']:
    r = c.table(t).select('*', count='exact').limit(1).execute()
    print(f'{t}: {r.count} rows')
"
```
Expected: `tickers: 6`, and non-zero counts for at least `prices`, `news`, `ingest_runs`. `earnings_dates` should include MU's 2026-06-24.

- [ ] **Step 4: Spot-check MU's earnings date is captured**

Run:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
uv run python -c "
from vanta.store import make_client
c = make_client()
r = c.table('earnings_dates').select('*').eq('ticker','MU').execute()
print(r.data)
"
```
Expected: a row with `report_date` `2026-06-24` for MU.

- [ ] **Step 5: Write the coverage findings doc + commit**

Create `vanta/docs/coverage-step1.md` summarizing actual per-source/per-ticker counts from Step 2's report, and explicitly noting any gaps (e.g., foreign peers, rate-limited sources). Then:
```bash
cd /Users/pratik.nandoskar/Documents/working/vanta
git add docs/coverage-step1.md
git commit -m "docs: step 1 live coverage findings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Decision gate:** review `docs/coverage-step1.md`. If the free intelligence is rich enough, proceed to Step 2 (buy ORATS/Polygon IV + options layer). If a source is too thin, swap/augment it before spending.

---

## Notes for the implementer

- **Run everything from the repo root** `/Users/pratik.nandoskar/Documents/working/vanta` so `.env` and `uv` resolve correctly.
- **`.env` already exists** (gitignored) with all keys. Never commit it.
- **Free-tier rate limits are real**: Alpha Vantage ~25 req/day, Finnhub 60 req/min, FMP 250 req/day. The orchestrator throttles 1s between calls in `main()`. If you hit a limit mid-run, that source logs a gap — expected, not a bug.
- **`SNDK`** (SanDisk) trades post its 2025 spin-off; if FMP/Finnhub lack history, that surfaces as a gap in the coverage report — capture it honestly rather than substituting another ticker.
- **Foreign peers (SK Hynix, Samsung)** are intentionally NOT in the Step-1 universe (US-API coverage is thin); they are a documented Step-2+ consideration.
