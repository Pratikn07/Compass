# Edge Live-Data Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble a `PointInTimeDataset` + historical earnings event spine + peer signals from free Alpha Vantage earnings history and Alpaca bars/options, feeding the already-built (frozen) edge backtest harness so the first real backtest can run.

**Architecture:** A new `src/prescient/edge/data/` subpackage of small single-purpose units behind clean interfaces: an `AlphaVantageEarningsHistoryAdapter` (behind an `EarningsHistoryProvider` Protocol), two thin Alpaca loaders (bars, options), a pure `peer_signals` builder, a `DatasetAssembler` orchestrator, and an on-disk fetch-once `cache`. A live `scripts/run_edge_backtest.py` wires real keys and prints the scorecard. The frozen `prescient.edge` scoring modules are NOT modified.

**Tech Stack:** Python >=3.11, Pydantic v2 (frozen, `extra="forbid"`), pytest, ruff (line-length 100), `uv`. Reuses `prescient.data.alpha_vantage` (transport), `prescient.data.alpaca_market` (`get_daily_bars`, `get_atm_option_quotes`), and `prescient.edge` (loader, runner, models).

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-05-edge-live-data-assembly-design.md` (read it first).

## Verified facts about the existing codebase

- **Alpha Vantage transport** lives in `src/prescient/data/alpha_vantage.py`:
  `SyncHttpClient` Protocol (`.get(url, *, params, timeout) -> SyncHttpResponse` with
  `.status_code` and `.json()`), and `_DefaultHttpClient`. The `EARNINGS` response shape
  (verified live) is `{"symbol", "annualEarnings", "quarterlyEarnings": [...]}` where
  each quarterly row has `fiscalDateEnding, reportedDate, reportedEPS, estimatedEPS,
  surprise, surprisePercentage, reportTime`. Rate-limit/None responses come back as a
  JSON object with a `"Note"` or `"Information"` key and HTTP 200.
- **Alpaca adapter** `AlpacaMarketDataAdapter` in `src/prescient/data/alpaca_market.py`:
  - `get_daily_bars(*, symbols: Sequence[str], start: date, end: date) -> dict[str, list[DailyBarSnapshot]]`
  - `get_atm_option_quotes(*, underlying_symbol: str, quote_date: date, earnings_date: date, max_expiration_date: date, feed="indicative") -> list[OptionQuote]`
- **Edge harness** (frozen):
  - `prescient.edge.loader.PointInTimeDataset(bars: dict[str, list[DailyBarSnapshot]], option_quotes: dict[str, list[OptionQuote]])`
  - `prescient.edge.loader.build_event_context(*, dataset, ticker, earnings_date, as_of_date, horizon_days) -> EventContext | None`
  - `EventContext` is FROZEN; attach peer signals via `.model_copy(update={...})`.
    Fields: `ticker, earnings_date, as_of_date, underlying_price, atm_call, atm_put,
    peer_eps_surprises: dict[str,float], peer_stock_reactions: dict[str,float], realized_move`.
  - `prescient.edge.runner.run_edge_backtest(*, contexts, strategies) -> EdgeBacktestResult`
  - strategies: `ReactionAwarePeerStrategy(), CoinFlipStrategy(), AlwaysUpStrategy()`
  - `prescient.edge.universe.load_edge_universe(path) -> EdgeUniverse` (`.tickers`)
- **Error model** `prescient.data.models.DataProviderError(provider: DataProvider,
  error_type: DataProviderErrorType, message, endpoint=None, status_code=None,
  symbol=None, retry_after_seconds=None)`; `DataProvider.ALPHA_VANTAGE` and
  `DataProvider.ALPACA` exist; `DataProviderErrorType` has `RATE_LIMITED`, `TIMEOUT`,
  `PROVIDER_UNAVAILABLE`, `MISSING_API_KEY`, `MALFORMED_RESPONSE`, `EMPTY_RESPONSE`.
- `ReportTime = Literal["BMO", "AMC", "UNKNOWN"]` (defined in `data/assembly.py:34` and
  `signal/models.py`). For the edge data layer we use plain `str` normalized to those
  three values to avoid cross-package coupling.
- `DailyBarSnapshot` (frozen): `ticker, trading_date: date, open/high/low/close: float|None,
  volume: int|None, vwap: float|None`.
- Tests live in `tests/`, run `uv run pytest`. TDD, frequent commits, ruff line-length 100.
- `.env` provides `ALPHAVANTAGE_API_KEY`, `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`.
- Live Alpaca SDK readers are built by
  `prescient.live_data.alpaca_readers.build_alpaca_sdk_readers(*, api_key_id, api_secret_key)`.

## File structure (each file one responsibility)

Create under `src/prescient/edge/data/`:
- `__init__.py` — package exports.
- `models.py` — `EarningsAnnouncement` (frozen) + `AssembledEdgeDataset` (frozen result).
- `earnings_history.py` — `EarningsHistoryProvider` Protocol +
  `AlphaVantageEarningsHistoryAdapter`.
- `bars_loader.py` — `load_daily_bars(adapter, *, tickers, start, end)`.
- `option_loader.py` — `load_option_quotes_for_events(adapter, *, events, max_expiration_days)`.
- `peer_signals.py` — pure `build_peer_signals(...)`.
- `assembler.py` — `DatasetAssembler` orchestrator.
- `cache.py` — on-disk fetch-once JSON cache.

Create `scripts/run_edge_backtest.py` (live command, not in test suite).
Create tests `tests/test_edge_data_*.py`.

Frozen scoring modules are NOT modified.

---

### Task 1: Data-layer models

**Files:**
- Create: `src/prescient/edge/data/__init__.py`
- Create: `src/prescient/edge/data/models.py`
- Test: `tests/test_edge_data_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_models.py
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


def test_earnings_announcement_normalizes_ticker_and_reporttime() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(
        ticker="mu",
        report_date=date(2024, 6, 26),
        report_time="amc",
        eps_estimate=1.2,
        eps_actual=1.45,
        surprise_pct=20.8,
    )
    assert ann.ticker == "MU"
    assert ann.report_time == "AMC"
    assert ann.eps_actual == 1.45


def test_earnings_announcement_unknown_reporttime_default() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))
    assert ann.report_time == "UNKNOWN"
    assert ann.eps_estimate is None


def test_earnings_announcement_is_frozen() -> None:
    from prescient.edge.data.models import EarningsAnnouncement

    ann = EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))
    with pytest.raises(ValidationError):
        ann.ticker = "NVDA"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'prescient.edge.data'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/__init__.py
"""Live-data assembly for the edge backtest harness.

See docs/superpowers/specs/2026-06-05-edge-live-data-assembly-design.md.
"""
```

```python
# src/prescient/edge/data/models.py
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

ReportTime = Literal["BMO", "AMC", "UNKNOWN"]


def _norm_ticker(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("Ticker must not be empty.")
    return cleaned


def _norm_report_time(value: str) -> str:
    cleaned = str(value).strip().upper()
    return cleaned if cleaned in ("BMO", "AMC", "UNKNOWN") else "UNKNOWN"


class EarningsAnnouncement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    report_date: date
    report_time: ReportTime = "UNKNOWN"
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return _norm_ticker(value)

    @field_validator("report_time", mode="before")
    @classmethod
    def normalize_report_time(cls, value: str) -> str:
        return _norm_report_time(value)


class AssembledEdgeDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    # event_contexts and dataset hold edge types; kept as objects to avoid importing
    # frozen scoring models into this layer's public schema.
    event_contexts: list[object]
    dataset: object
    events_total: int
    events_dropped: int
    drop_reasons: dict[str, int]
    errors: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/__init__.py src/prescient/edge/data/models.py tests/test_edge_data_models.py
git commit -m "feat(edge-data): earnings announcement + assembled-dataset models"
```

---

### Task 2: Alpha Vantage earnings-history adapter

**Files:**
- Create: `src/prescient/edge/data/earnings_history.py`
- Test: `tests/test_edge_data_earnings_history.py`

Reuses the `SyncHttpClient` transport contract from `prescient.data.alpha_vantage`.
One `EARNINGS` call per ticker; maps `quarterlyEarnings[]` rows; filters to `[start, end]`
by `reportedDate`; rate-limit/None payloads -> RATE_LIMITED error; missing key ->
MISSING_API_KEY; timeout/transport -> TIMEOUT/PROVIDER_UNAVAILABLE.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_earnings_history.py
from __future__ import annotations

from datetime import date
from typing import Any


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class FakeClient:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        return FakeResponse(self._payload)


_MU_PAYLOAD = {
    "symbol": "MU",
    "quarterlyEarnings": [
        {
            "fiscalDateEnding": "2024-05-31",
            "reportedDate": "2024-06-26",
            "reportedEPS": "1.45",
            "estimatedEPS": "1.20",
            "surprise": "0.25",
            "surprisePercentage": "20.83",
            "reportTime": "post-market",
        },
        {
            "fiscalDateEnding": "2023-02-28",
            "reportedDate": "2023-03-28",
            "reportedEPS": "-1.91",
            "estimatedEPS": "-0.86",
            "surprise": "-1.05",
            "surprisePercentage": "-122.0",
            "reportTime": "post-market",
        },
    ],
}


def test_maps_quarterly_rows_and_filters_window() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    adapter = AlphaVantageEarningsHistoryAdapter(
        api_key="k", http_client=FakeClient(_MU_PAYLOAD)
    )
    anns, errors = adapter.get_earnings_history(
        tickers=["mu"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert errors == []
    assert len(anns) == 1  # 2023 row filtered out
    a = anns[0]
    assert a.ticker == "MU"
    assert a.report_date == date(2024, 6, 26)
    assert a.report_time == "AMC"  # "post-market" -> AMC
    assert a.eps_actual == 1.45
    assert a.eps_estimate == 1.20
    assert a.surprise_pct == 20.83


def test_missing_key_returns_error_no_call() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    client = FakeClient(_MU_PAYLOAD)
    adapter = AlphaVantageEarningsHistoryAdapter(api_key="", http_client=client)
    anns, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert anns == []
    assert len(errors) == 1
    assert client.calls == []


def test_rate_limit_note_becomes_error() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    note = {"Information": "rate limit reached, please subscribe"}
    adapter = AlphaVantageEarningsHistoryAdapter(api_key="k", http_client=FakeClient(note))
    anns, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert anns == []
    assert len(errors) == 1
    assert "secret" not in repr(errors[0]).lower()


def test_secret_not_leaked_in_errors() -> None:
    from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter

    note = {"Note": "Thank you for using Alpha Vantage"}
    adapter = AlphaVantageEarningsHistoryAdapter(
        api_key="super-secret-key", http_client=FakeClient(note)
    )
    _, errors = adapter.get_earnings_history(
        tickers=["MU"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert "super-secret-key" not in repr([e.model_dump(mode="json") for e in errors])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_earnings_history.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/earnings_history.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol, Sequence

import httpx

from prescient.data.models import DataProvider, DataProviderError, DataProviderErrorType
from prescient.edge.data.models import EarningsAnnouncement

_EARNINGS_FUNCTION = "EARNINGS"
_QUERY_PATH = "/query"
_REPORT_TIME_MAP = {
    "pre-market": "BMO",
    "post-market": "AMC",
    "bmo": "BMO",
    "amc": "AMC",
}


class SyncHttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class SyncHttpClient(Protocol):
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> SyncHttpResponse: ...


class _DefaultHttpClient:
    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> SyncHttpResponse:
        return httpx.get(url, params=params, timeout=timeout)


class EarningsHistoryProvider(Protocol):
    def get_earnings_history(
        self, *, tickers: Sequence[str], start: date, end: date
    ) -> tuple[list[EarningsAnnouncement], list[DataProviderError]]: ...


def _err(error_type: DataProviderErrorType, message: str, symbol: str | None = None,
         status_code: int | None = None) -> DataProviderError:
    return DataProviderError(
        provider=DataProvider.ALPHA_VANTAGE,
        error_type=error_type,
        message=message,
        endpoint=_QUERY_PATH,
        status_code=status_code,
        symbol=symbol,
    )


def _to_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


class AlphaVantageEarningsHistoryAdapter:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://www.alphavantage.co",
        timeout_seconds: float = 15.0,
        http_client: SyncHttpClient | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else ""
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client or _DefaultHttpClient()

    def get_earnings_history(
        self, *, tickers: Sequence[str], start: date, end: date
    ) -> tuple[list[EarningsAnnouncement], list[DataProviderError]]:
        announcements: list[EarningsAnnouncement] = []
        errors: list[DataProviderError] = []
        if not self._api_key:
            errors.append(_err(DataProviderErrorType.MISSING_API_KEY,
                               "Alpha Vantage API key is required for earnings history."))
            return announcements, errors

        seen: set[str] = set()
        for raw in tickers:
            symbol = raw.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            payload = self._fetch(symbol, errors)
            if payload is None:
                continue
            quarterly = payload.get("quarterlyEarnings")
            if not isinstance(quarterly, list):
                # Rate-limit / info payloads have no quarterlyEarnings list.
                errors.append(_err(DataProviderErrorType.RATE_LIMITED,
                                   "Alpha Vantage returned no earnings data "
                                   "(rate limit or empty).", symbol=symbol))
                continue
            for row in quarterly:
                if not isinstance(row, dict):
                    continue
                report_date = _parse_date(row.get("reportedDate"))
                if report_date is None or not (start <= report_date <= end):
                    continue
                announcements.append(
                    EarningsAnnouncement(
                        ticker=symbol,
                        report_date=report_date,
                        report_time=_REPORT_TIME_MAP.get(
                            str(row.get("reportTime", "")).strip().lower(), "UNKNOWN"
                        ),
                        eps_estimate=_to_float(row.get("estimatedEPS")),
                        eps_actual=_to_float(row.get("reportedEPS")),
                        surprise_pct=_to_float(row.get("surprisePercentage")),
                    )
                )
        return announcements, errors

    def _fetch(self, symbol: str, errors: list[DataProviderError]) -> dict[str, Any] | None:
        params = {"function": _EARNINGS_FUNCTION, "symbol": symbol, "apikey": self._api_key}
        try:
            response = self._http_client.get(
                f"{self._base_url}{_QUERY_PATH}", params=params, timeout=self._timeout_seconds
            )
        except (TimeoutError, httpx.TimeoutException):
            errors.append(_err(DataProviderErrorType.TIMEOUT,
                               "Alpha Vantage earnings request timed out.", symbol=symbol))
            return None
        except httpx.HTTPError:
            errors.append(_err(DataProviderErrorType.PROVIDER_UNAVAILABLE,
                               "Alpha Vantage earnings provider is unavailable.", symbol=symbol))
            return None
        if response.status_code != 200:
            errors.append(_err(DataProviderErrorType.PROVIDER_UNAVAILABLE,
                               "Alpha Vantage earnings returned a non-200 status.",
                               symbol=symbol, status_code=response.status_code))
            return None
        try:
            payload = response.json()
        except ValueError:
            errors.append(_err(DataProviderErrorType.MALFORMED_RESPONSE,
                               "Alpha Vantage earnings returned malformed JSON.", symbol=symbol))
            return None
        if not isinstance(payload, dict):
            errors.append(_err(DataProviderErrorType.MALFORMED_RESPONSE,
                               "Alpha Vantage earnings payload was not an object.", symbol=symbol))
            return None
        return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_earnings_history.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/earnings_history.py tests/test_edge_data_earnings_history.py
git commit -m "feat(edge-data): Alpha Vantage earnings-history adapter"
```

---

### Task 3: Bars loader

**Files:**
- Create: `src/prescient/edge/data/bars_loader.py`
- Test: `tests/test_edge_data_bars_loader.py`

Thin wrapper over `AlpacaMarketDataAdapter.get_daily_bars` (batched multi-symbol).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_bars_loader.py
from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot


class FakeBarsAdapter:
    def __init__(self, data):
        self._data = data
        self.calls = []

    def get_daily_bars(self, *, symbols, start, end):
        self.calls.append({"symbols": list(symbols), "start": start, "end": end})
        return self._data


def test_load_daily_bars_passes_through_and_batches() -> None:
    from prescient.edge.data.bars_loader import load_daily_bars

    data = {"MU": [DailyBarSnapshot(ticker="MU", trading_date=date(2024, 6, 25), close=100.0)]}
    adapter = FakeBarsAdapter(data)
    out = load_daily_bars(
        adapter, tickers=["MU", "NVDA"], start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert out == data
    assert adapter.calls == [
        {"symbols": ["MU", "NVDA"], "start": date(2024, 1, 1), "end": date(2024, 12, 31)}
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_bars_loader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/bars_loader.py
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from prescient.data.models import DailyBarSnapshot


def load_daily_bars(
    adapter: Any, *, tickers: Sequence[str], start: date, end: date
) -> dict[str, list[DailyBarSnapshot]]:
    """One batched multi-symbol Alpaca call for the full window."""
    return adapter.get_daily_bars(symbols=list(tickers), start=start, end=end)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_bars_loader.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/bars_loader.py tests/test_edge_data_bars_loader.py
git commit -m "feat(edge-data): batched Alpaca daily-bars loader"
```

---

### Task 4: Option-quote loader for events

**Files:**
- Create: `src/prescient/edge/data/option_loader.py`
- Test: `tests/test_edge_data_option_loader.py`

For each announcement, fetch the pre-earnings ATM straddle window via
`get_atm_option_quotes`, accumulating per-ticker quotes. `max_expiration_date =
report_date + max_expiration_days`. `quote_date` = `report_date` (the dataset's
`option_quotes_as_of` later filters to `<= as_of_date`; here we just tag fetch date).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_option_loader.py
from __future__ import annotations

from datetime import date

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


class FakeOptionAdapter:
    def __init__(self):
        self.calls = []

    def get_atm_option_quotes(self, *, underlying_symbol, quote_date, earnings_date,
                              max_expiration_date, feed="indicative"):
        self.calls.append({
            "symbol": underlying_symbol, "quote_date": quote_date,
            "earnings_date": earnings_date, "max_expiration_date": max_expiration_date,
        })
        return [
            OptionQuote(ticker=underlying_symbol, option_type="CALL", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=quote_date,
                        bid=3.9, ask=4.1),
            OptionQuote(ticker=underlying_symbol, option_type="PUT", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=quote_date,
                        bid=3.9, ask=4.1),
        ]


def test_loads_quotes_per_event_and_accumulates_by_ticker() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 3, 20)),
    ]
    adapter = FakeOptionAdapter()
    out = load_option_quotes_for_events(adapter, events=events, max_expiration_days=14)
    assert set(out.keys()) == {"MU"}
    assert len(out["MU"]) == 4  # 2 legs x 2 events
    assert len(adapter.calls) == 2
    # max_expiration_date = report_date + 14 days
    assert adapter.calls[0]["max_expiration_date"] == date(2024, 7, 10)


def test_continues_when_one_event_errors() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    class FlakyAdapter(FakeOptionAdapter):
        def get_atm_option_quotes(self, **kwargs):
            if kwargs["underlying_symbol"] == "BAD":
                raise RuntimeError("boom")
            return super().get_atm_option_quotes(**kwargs)

    events = [
        EarningsAnnouncement(ticker="BAD", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
    ]
    out = load_option_quotes_for_events(FlakyAdapter(), events=events, max_expiration_days=14)
    assert "MU" in out and "BAD" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_option_loader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/option_loader.py
from __future__ import annotations

from datetime import timedelta
from typing import Any, Sequence

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def load_option_quotes_for_events(
    adapter: Any, *, events: Sequence[EarningsAnnouncement], max_expiration_days: int
) -> dict[str, list[OptionQuote]]:
    """One ATM-chain pull per event; accumulate per ticker. A failed event is
    skipped (skip-not-guess), never zero-filled."""
    out: dict[str, list[OptionQuote]] = {}
    for event in events:
        max_exp = event.report_date + timedelta(days=max_expiration_days)
        try:
            quotes = adapter.get_atm_option_quotes(
                underlying_symbol=event.ticker,
                quote_date=event.report_date,
                earnings_date=event.report_date,
                max_expiration_date=max_exp,
            )
        except Exception:
            continue
        if quotes:
            out.setdefault(event.ticker, []).extend(quotes)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_option_loader.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/option_loader.py tests/test_edge_data_option_loader.py
git commit -m "feat(edge-data): per-event ATM option-quote loader"
```

---

### Task 5: Peer-signal builder (pure — the no-lookahead core)

**Files:**
- Create: `src/prescient/edge/data/peer_signals.py`
- Test: `tests/test_edge_data_peer_signals.py`

Given a target's `as_of_date` and all announcements + bars, returns
`(peer_eps_surprises, peer_stock_reactions)`. A peer counts ONLY if
`peer.report_date < target_as_of_date` AND within trailing `peer_window_days`.
Surprise prefers `surprise_pct`, else computes from est/actual. Reaction is the
close-before -> close-after the peer's report (omit peer if either close missing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_peer_signals.py
from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement


def _bar(t, d, c):
    return DailyBarSnapshot(ticker=t, trading_date=d, close=c)


def test_excludes_peer_reporting_on_or_after_target_as_of() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    target_as_of = date(2024, 6, 25)
    anns = [
        # in-window peer BEFORE as_of -> included
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                             surprise_pct=8.0),
        # peer reporting AFTER target as_of -> MUST be excluded (lookahead)
        EarningsAnnouncement(ticker="AVGO", report_date=date(2024, 6, 26),
                             surprise_pct=5.0),
    ]
    bars = {
        "NVDA": [
            _bar("NVDA", date(2024, 6, 11), 100.0),  # close before report
            _bar("NVDA", date(2024, 6, 12), 101.0),
            _bar("NVDA", date(2024, 6, 13), 106.0),  # close after report -> +6%
        ],
    }
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=target_as_of, announcements=anns,
        bars=bars, peer_window_days=21,
    )
    assert "NVDA" in surprises and "AVGO" not in surprises
    assert surprises["NVDA"] == 8.0
    assert reactions["NVDA"] == 6.0  # 100 -> 106


def test_excludes_peer_outside_trailing_window() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 5, 1),
                             surprise_pct=8.0),  # >21d before as_of
    ]
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises == {} and reactions == {}


def test_target_itself_never_a_peer() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 12),
                                 surprise_pct=3.0)]
    surprises, _ = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises == {}


def test_surprise_computed_from_eps_when_pct_absent() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                                 eps_estimate=1.0, eps_actual=1.1)]
    surprises, _ = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert round(surprises["NVDA"], 4) == 10.0  # (1.1-1.0)/1.0*100


def test_peer_omitted_when_reaction_bars_missing() -> None:
    from prescient.edge.data.peer_signals import build_peer_signals

    anns = [EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                                 surprise_pct=8.0)]
    surprises, reactions = build_peer_signals(
        target="MU", target_as_of_date=date(2024, 6, 25), announcements=anns,
        bars={}, peer_window_days=21,
    )
    assert surprises["NVDA"] == 8.0       # surprise still known
    assert "NVDA" not in reactions        # but reaction omitted (no bars)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_peer_signals.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/peer_signals.py
from __future__ import annotations

from datetime import date, timedelta

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement


def _surprise_pct(ann: EarningsAnnouncement) -> float | None:
    if ann.surprise_pct is not None:
        return ann.surprise_pct
    if ann.eps_estimate is not None and ann.eps_actual is not None and ann.eps_estimate != 0:
        return ((ann.eps_actual - ann.eps_estimate) / abs(ann.eps_estimate)) * 100.0
    return None


def _reaction_pct(
    bars: list[DailyBarSnapshot], report_date: date
) -> float | None:
    """Close the trading day before report -> close the trading day after."""
    ordered = sorted(bars, key=lambda b: b.trading_date)
    before = [b for b in ordered if b.trading_date < report_date and b.close is not None]
    after = [b for b in ordered if b.trading_date > report_date and b.close is not None]
    if not before or not after:
        return None
    pre = before[-1].close
    post = after[0].close
    if pre is None or post is None or pre <= 0:
        return None
    return ((post - pre) / pre) * 100.0


def build_peer_signals(
    *,
    target: str,
    target_as_of_date: date,
    announcements: list[EarningsAnnouncement],
    bars: dict[str, list[DailyBarSnapshot]],
    peer_window_days: int,
) -> tuple[dict[str, float], dict[str, float]]:
    target = target.strip().upper()
    window_start = target_as_of_date - timedelta(days=peer_window_days)
    surprises: dict[str, float] = {}
    reactions: dict[str, float] = {}
    seen: set[str] = set()

    for ann in announcements:
        peer = ann.ticker
        if peer == target or peer in seen:
            continue
        # No-lookahead: peer must have reported strictly before the target's anchor,
        # and within the trailing window.
        if not (window_start <= ann.report_date < target_as_of_date):
            continue
        surprise = _surprise_pct(ann)
        if surprise is None:
            continue
        seen.add(peer)
        surprises[peer] = surprise
        reaction = _reaction_pct(bars.get(peer, []), ann.report_date)
        if reaction is not None:
            reactions[peer] = reaction

    return surprises, reactions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_peer_signals.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/peer_signals.py tests/test_edge_data_peer_signals.py
git commit -m "feat(edge-data): pure peer-signal builder with no-lookahead filter"
```

---

### Task 6: On-disk fetch-once cache

**Files:**
- Create: `src/prescient/edge/data/cache.py`
- Test: `tests/test_edge_data_cache.py`

A tiny JSON cache: `get(key)` returns parsed JSON or None; `put(key, value)` writes it.
Keys are slugified to safe filenames under a cache dir. No secrets are ever passed in
(callers cache normalized data only).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_cache.py
from __future__ import annotations


def test_put_then_get_roundtrips(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    assert cache.get("earnings:MU:2024") is None
    cache.put("earnings:MU:2024", {"rows": [1, 2, 3]})
    assert cache.get("earnings:MU:2024") == {"rows": [1, 2, 3]}


def test_keys_with_unsafe_chars_are_isolated(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    cache.put("a/b:c d", {"x": 1})
    cache.put("a_b_c_d_other", {"x": 2})
    assert cache.get("a/b:c d") == {"x": 1}


def test_corrupt_file_returns_none(tmp_path) -> None:
    from prescient.edge.data.cache import JsonFileCache

    cache = JsonFileCache(tmp_path)
    cache.put("k", {"x": 1})
    # corrupt it
    for p in tmp_path.iterdir():
        p.write_text("not json", encoding="utf-8")
    assert cache.get("k") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/cache.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class JsonFileCache:
    """Fetch-once on-disk JSON cache. Keys are hashed to safe filenames. Callers
    must only store normalized, secret-free data."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

    def put(self, key: str, value: Any) -> None:
        self._path(key).write_text(json.dumps(value), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_cache.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/cache.py tests/test_edge_data_cache.py
git commit -m "feat(edge-data): on-disk fetch-once JSON cache"
```

---

### Task 7: Dataset assembler (orchestrator)

**Files:**
- Create: `src/prescient/edge/data/assembler.py`
- Test: `tests/test_edge_data_assembler.py`

Pure orchestration over already-fetched inputs (announcements, bars, option_quotes) —
NO network here, so it is fully unit-testable. Builds `PointInTimeDataset`, derives
`as_of_date = report_date - 1 day`, calls `build_event_context`, attaches peer signals
via `model_copy`, drops events with no context (logged in `drop_reasons`), returns
`AssembledEdgeDataset`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_assembler.py
from __future__ import annotations

from datetime import date

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def _bar(t, d, c):
    return DailyBarSnapshot(ticker=t, trading_date=d, close=c)


def _straddle(t, qd):
    return [
        OptionQuote(ticker=t, option_type="CALL", strike=100.0,
                    expiration_date=date(2024, 6, 28), quote_date=qd, bid=3.9, ask=4.1),
        OptionQuote(ticker=t, option_type="PUT", strike=100.0,
                    expiration_date=date(2024, 6, 28), quote_date=qd, bid=3.9, ask=4.1),
    ]


def test_assembles_context_with_peer_signals_and_drops_uncovered() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    # Target MU reports 2024-06-26 -> as_of 2024-06-25.
    # Peer NVDA reported 2024-06-12 (before as_of, in window) with +8% surprise.
    announcements = [
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26),
                             eps_estimate=1.2, eps_actual=1.45, surprise_pct=20.8),
        EarningsAnnouncement(ticker="NVDA", report_date=date(2024, 6, 12),
                             surprise_pct=8.0),
        # event with no bars at all -> dropped
        EarningsAnnouncement(ticker="GHOST", report_date=date(2024, 6, 20)),
    ]
    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 24), 99.0),
            _bar("MU", date(2024, 6, 25), 100.0),   # as_of close
            _bar("MU", date(2024, 6, 26), 103.0),
            _bar("MU", date(2024, 6, 27), 106.0),   # +6% realized at horizon 2
        ],
        "NVDA": [
            _bar("NVDA", date(2024, 6, 11), 100.0),
            _bar("NVDA", date(2024, 6, 13), 106.0),
        ],
    }
    option_quotes = {"MU": _straddle("MU", date(2024, 6, 25))}

    result = assemble_edge_dataset(
        announcements=announcements, bars=bars, option_quotes=option_quotes,
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    assert len(result.event_contexts) == 1
    ctx = result.event_contexts[0]
    assert ctx.ticker == "MU"
    assert ctx.as_of_date == date(2024, 6, 25)
    assert ctx.underlying_price == 100.0
    assert ctx.peer_eps_surprises == {"NVDA": 8.0}
    assert ctx.peer_stock_reactions == {"NVDA": 6.0}
    assert ctx.realized_move is not None


def test_drops_event_without_asof_price() -> None:
    from prescient.edge.data.assembler import assemble_edge_dataset

    announcements = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    result = assemble_edge_dataset(
        announcements=announcements, bars={}, option_quotes={},
        target_tickers=["MU"], horizon_days=2, peer_window_days=21,
    )
    assert result.event_contexts == []
    assert result.events_dropped == 1
    assert result.drop_reasons.get("no_event_context", 0) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_assembler.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# src/prescient/edge/data/assembler.py
from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from prescient.data.models import DailyBarSnapshot
from prescient.edge.data.models import AssembledEdgeDataset, EarningsAnnouncement
from prescient.edge.data.peer_signals import build_peer_signals
from prescient.edge.loader import PointInTimeDataset, build_event_context
from prescient.edge.models import OptionQuote


def assemble_edge_dataset(
    *,
    announcements: Sequence[EarningsAnnouncement],
    bars: dict[str, list[DailyBarSnapshot]],
    option_quotes: dict[str, list[OptionQuote]],
    target_tickers: Sequence[str],
    horizon_days: int,
    peer_window_days: int,
) -> AssembledEdgeDataset:
    dataset = PointInTimeDataset(bars=bars, option_quotes=option_quotes)
    targets = {t.strip().upper() for t in target_tickers}

    contexts: list[object] = []
    dropped = 0
    drop_reasons: dict[str, int] = {}
    total = 0

    for ann in announcements:
        if ann.ticker not in targets:
            continue
        total += 1
        as_of_date = ann.report_date - timedelta(days=1)
        ctx = build_event_context(
            dataset=dataset,
            ticker=ann.ticker,
            earnings_date=ann.report_date,
            as_of_date=as_of_date,
            horizon_days=horizon_days,
        )
        if ctx is None:
            dropped += 1
            drop_reasons["no_event_context"] = drop_reasons.get("no_event_context", 0) + 1
            continue
        surprises, reactions = build_peer_signals(
            target=ann.ticker,
            target_as_of_date=as_of_date,
            announcements=list(announcements),
            bars=bars,
            peer_window_days=peer_window_days,
        )
        contexts.append(
            ctx.model_copy(
                update={"peer_eps_surprises": surprises, "peer_stock_reactions": reactions}
            )
        )

    return AssembledEdgeDataset(
        event_contexts=contexts,
        dataset=dataset,
        events_total=total,
        events_dropped=dropped,
        drop_reasons=drop_reasons,
        errors=[],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_assembler.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/prescient/edge/data/assembler.py tests/test_edge_data_assembler.py
git commit -m "feat(edge-data): dataset assembler (contexts + peer signals + coverage)"
```

---

### Task 8: Package exports + full-suite green + lint gate

**Files:**
- Modify: `src/prescient/edge/data/__init__.py`
- Test: none (verification task)

- [ ] **Step 1: Add exports to `src/prescient/edge/data/__init__.py`**

Append after the existing module docstring:

```python
from prescient.edge.data.assembler import assemble_edge_dataset
from prescient.edge.data.bars_loader import load_daily_bars
from prescient.edge.data.cache import JsonFileCache
from prescient.edge.data.earnings_history import (
    AlphaVantageEarningsHistoryAdapter,
    EarningsHistoryProvider,
)
from prescient.edge.data.models import AssembledEdgeDataset, EarningsAnnouncement
from prescient.edge.data.option_loader import load_option_quotes_for_events
from prescient.edge.data.peer_signals import build_peer_signals

__all__ = [
    "AlphaVantageEarningsHistoryAdapter",
    "AssembledEdgeDataset",
    "EarningsAnnouncement",
    "EarningsHistoryProvider",
    "JsonFileCache",
    "assemble_edge_dataset",
    "build_peer_signals",
    "load_daily_bars",
    "load_option_quotes_for_events",
]
```

- [ ] **Step 2: Confirm package imports**

Run: `uv run python -c "import prescient.edge.data as d; print(sorted(d.__all__))"`
Expected: prints the export list with no import error.

- [ ] **Step 3: Run the edge-data suite**

Run: `uv run pytest tests/ -k edge_data -v`
Expected: all edge-data tests PASS.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all pre-existing tests still PASS (the new subpackage touches no existing code).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/prescient/edge/data tests
git add src/prescient/edge/data/__init__.py
git commit -m "feat(edge-data): package exports + green/lint gate"
```

---

### Task 9: Live runner script

**Files:**
- Create: `scripts/run_edge_backtest.py`
- Test: none (live command; pure pieces already unit-tested). Smoke-import only.

Wires real keys: builds the AV earnings adapter + the live Alpaca adapter (via
`build_alpaca_sdk_readers`), fetches earnings (cached) -> bars -> options -> assembles ->
runs `run_edge_backtest` -> prints scorecards + coverage. `--limit N` caps events for a
cheap first run.

- [ ] **Step 1: Write the script**

```python
# scripts/run_edge_backtest.py
"""Run the edge backtest against live data (Alpha Vantage earnings + Alpaca
bars/options). Requires ALPHAVANTAGE_API_KEY, ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY.

Usage:
  uv run python scripts/run_edge_backtest.py --limit 20   # cheap smoke test
  uv run python scripts/run_edge_backtest.py              # full run

Caches earnings history on disk (fetch-once) under .cache/edge/.
Propose-only research tooling: it never places, sizes, or suggests a trade.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from prescient.data.alpaca_market import AlpacaMarketDataAdapter
from prescient.edge.data.assembler import assemble_edge_dataset
from prescient.edge.data.bars_loader import load_daily_bars
from prescient.edge.data.cache import JsonFileCache
from prescient.edge.data.earnings_history import AlphaVantageEarningsHistoryAdapter
from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.data.option_loader import load_option_quotes_for_events
from prescient.edge.runner import run_edge_backtest
from prescient.edge.strategy import (
    AlwaysUpStrategy,
    CoinFlipStrategy,
    ReactionAwarePeerStrategy,
)
from prescient.edge.universe import load_edge_universe
from prescient.live_data.alpaca_readers import build_alpaca_sdk_readers

_HORIZON_DAYS = 2
_PEER_WINDOW_DAYS = 21
_MAX_EXPIRATION_DAYS = 14


def _cached_earnings(cache, adapter, tickers, start, end):
    out: list[EarningsAnnouncement] = []
    to_fetch: list[str] = []
    for ticker in tickers:
        cached = cache.get(f"earnings:{ticker}")
        if cached is None:
            to_fetch.append(ticker)
        else:
            out.extend(
                EarningsAnnouncement(**row)
                for row in cached
                if start.isoformat() <= row["report_date"] <= end.isoformat()
            )
    if to_fetch:
        fetched, errors = adapter.get_earnings_history(
            tickers=to_fetch, start=date(2000, 1, 1), end=end
        )
        for err in errors:
            print(f"  earnings error: {err.error_type.value} {err.symbol or ''}")
        by_ticker: dict[str, list[dict]] = {}
        for ann in fetched:
            by_ticker.setdefault(ann.ticker, []).append(ann.model_dump(mode="json"))
        for ticker, rows in by_ticker.items():
            cache.put(f"earnings:{ticker}", rows)
        out.extend(a for a in fetched if start <= a.report_date <= end)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="cap number of target events (cheap smoke test)")
    parser.add_argument("--years", type=int, default=2)
    args = parser.parse_args()

    load_dotenv()
    av_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    alpaca_id = os.environ.get("ALPACA_API_KEY_ID")
    alpaca_secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not (av_key and alpaca_id and alpaca_secret):
        raise SystemExit("Missing ALPHAVANTAGE_API_KEY / ALPACA_API_KEY_ID / "
                         "ALPACA_API_SECRET_KEY in env.")

    end = date.today()
    start = end - timedelta(days=365 * args.years)

    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    tickers = universe.tickers
    print(f"Universe: {len(tickers)} tickers | window {start} -> {end}")

    cache = JsonFileCache(Path(".cache/edge"))
    av = AlphaVantageEarningsHistoryAdapter(api_key=av_key)
    announcements = _cached_earnings(cache, av, tickers, start, end)
    print(f"Earnings announcements in window: {len(announcements)}")

    option_reader, bars_reader = build_alpaca_sdk_readers(
        api_key_id=alpaca_id, api_secret_key=alpaca_secret
    )
    alpaca = AlpacaMarketDataAdapter(
        option_chain_reader=option_reader, daily_bars_reader=bars_reader
    )

    bars = load_daily_bars(alpaca, tickers=tickers, start=start, end=end)
    print(f"Tickers with bars: {len(bars)}")

    target_events = sorted(announcements, key=lambda a: a.report_date, reverse=True)
    if args.limit is not None:
        target_events = target_events[: args.limit]
        print(f"Limited to {len(target_events)} most-recent events for smoke test.")

    option_quotes = load_option_quotes_for_events(
        alpaca, events=target_events, max_expiration_days=_MAX_EXPIRATION_DAYS
    )
    print(f"Tickers with option quotes: {len(option_quotes)}")

    result = assemble_edge_dataset(
        announcements=announcements,
        bars=bars,
        option_quotes=option_quotes,
        target_tickers=[a.ticker for a in target_events],
        horizon_days=_HORIZON_DAYS,
        peer_window_days=_PEER_WINDOW_DAYS,
    )
    print(f"\nCoverage: {len(result.event_contexts)}/{result.events_total} evaluable; "
          f"{result.events_dropped} dropped {result.drop_reasons}")

    backtest = run_edge_backtest(
        contexts=result.event_contexts,
        strategies=[ReactionAwarePeerStrategy(), CoinFlipStrategy(), AlwaysUpStrategy()],
    )

    print("\n=== SCORECARDS ===")
    header = f"{'strategy':24} {'eval':>5} {'dir%':>6} {'beat%':>6} {'avgRet%':>8} {'medRet%':>8} {'survived':>9}"
    print(header)
    for source, card in backtest.scorecards.items():
        print(f"{source:24} {card.events_evaluable:>5} "
              f"{_fmt(card.directional_hit_rate):>6} {_fmt(card.beat_implied_rate):>6} "
              f"{_fmt(card.average_option_return_pct):>8} "
              f"{_fmt(card.median_option_return_pct):>8} {str(card.survived):>9}")
        for note in card.notes:
            print(f"    note: {note}")
    print(f"\nsample size: "
          f"{backtest.scorecards.get('reaction_aware_peer').sample_size_verdict.value}")


def _fmt(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "-"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-import (no live call)**

Run: `uv run python -c "import ast; ast.parse(open('scripts/run_edge_backtest.py').read()); print('parses ok')"`
Expected: `parses ok`

- [ ] **Step 3: Lint**

Run: `uv run ruff check scripts/run_edge_backtest.py`
Expected: clean (fix any line-length issues, keep <=100).

- [ ] **Step 4: Add cache dir to .gitignore**

Append `.cache/` to `.gitignore` if not already present (check first with
`grep -q "^.cache/" .gitignore || echo ".cache/" >> .gitignore`).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_edge_backtest.py .gitignore
git commit -m "feat(edge-data): live run_edge_backtest script (Alpha Vantage + Alpaca)"
```

---

## Self-Review

**1. Spec coverage:**
- Swappable `EarningsHistoryProvider` + AV adapter → Task 2. ✓
- `EarningsAnnouncement` with surprise_pct + report_time → Task 1. ✓
- Bars loader (batched) → Task 3. ✓
- Option loader (per-event, skip-not-guess) → Task 4. ✓
- Peer-signal builder with the `report_date < as_of_date` filter + close-to-close
  reaction + surprise-prefers-pct → Task 5. ✓
- Fetch-once cache → Task 6. ✓
- DatasetAssembler (as_of = report_date - 1, model_copy peers, drop+coverage) → Task 7. ✓
- Package exports + green/lint → Task 8. ✓
- Live command with `--limit`, coverage summary, scorecard table → Task 9. ✓
- No-lookahead discipline → enforced in Task 5 (peer filter) + reuse of the frozen
  loader's as-of accessors in Task 7. ✓
- Skip-not-guess → Tasks 4 (option failure), 5 (missing bars), 7 (no-context drop). ✓
- Propose-only → nothing imports or calls broker/risk execution; script docstring states it. ✓
- No scoring changes → only `prescient.edge.data` (new) + scripts touched. ✓

**2. Placeholder scan:** No TBD/TODO; every code step is complete.

**3. Type consistency:**
- `EarningsAnnouncement` fields (ticker, report_date, report_time, eps_estimate,
  eps_actual, surprise_pct) consistent across Tasks 1, 2, 5, 7, 9.
- `get_earnings_history(*, tickers, start, end) -> (list, list)` consistent (Tasks 2, 9).
- `build_peer_signals(*, target, target_as_of_date, announcements, bars, peer_window_days)`
  consistent (Tasks 5, 7).
- `assemble_edge_dataset(*, announcements, bars, option_quotes, target_tickers,
  horizon_days, peer_window_days)` consistent (Tasks 7, 9).
- `load_daily_bars(adapter, *, tickers, start, end)` and
  `load_option_quotes_for_events(adapter, *, events, max_expiration_days)` consistent
  (Tasks 3/4/9).
- `AssembledEdgeDataset` fields (event_contexts, dataset, events_total, events_dropped,
  drop_reasons, errors) consistent (Tasks 1, 7, 9).

(Self-review typo corrected: the propose-only bullet should read "nothing imports or
calls broker/risk execution".)

## Notes / deferred

- The assembler is network-free and fully unit-tested; only `scripts/run_edge_backtest.py`
  performs live I/O and is intentionally excluded from the test suite (needs keys).
- AV free-tier rate limits (~25/day) are absorbed by the per-ticker fetch-once cache; a
  full 25-name fetch fits one day and is cached thereafter.
- Reaction definition is close-before -> close-after (per spec); multi-day drift is a
  later refinement if the backtest survives.
