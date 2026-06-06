# Historical-Options Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch the as-of-date ATM CALL+PUT straddle for each past earnings event (via Alpaca expired-contract listing + historical option bars), so the edge backtest's implied-move metric becomes computable and the option axis of the scorecard is populated.

**Architecture:** A pure, fake-testable `get_historical_atm_straddle` method on the existing `AlpacaMarketDataAdapter` (takes an injected reader, picks the ATM strike nearest a passed-in underlying price, prices each leg at the bar close), an SDK-bound `build_historical_option_reader` in the live_data layer (lists expired contracts + batches historical bars), an `as_of_price_for` helper in the assembler, and a rewired option loader that threads the underlying price through. The frozen scoring modules are untouched.

**Tech Stack:** Python >=3.11, Pydantic v2, pytest, ruff (line-length 100), `uv`, alpaca-py. Reuses `prescient.edge.models.OptionQuote`, `prescient.data.models.DailyBarSnapshot`, the existing injected-reader pattern in `AlpacaMarketDataAdapter`, and the existing `JsonFileCache`.

---

## Design reference

Spec: `docs/superpowers/specs/2026-06-05-historical-options-reader-design.md` (read it first).

## Verified facts about the existing codebase

- `AlpacaMarketDataAdapter.__init__(*, option_chain_reader=None, daily_bars_reader=None,
  error_sink=None)` (`src/prescient/data/alpaca_market.py:54`). It has `self._record(
  error_type, message, *, symbol=None)` and a module-level `_classify(exc) ->
  (DataProviderErrorType, str)`. Reader type aliases are `Callable[...]`.
- Existing `get_atm_option_quotes` is the CURRENT-chain sibling — leave it untouched.
- `OptionQuote` (`src/prescient/edge/models.py:41`): frozen, fields `ticker, option_type:
  Literal["CALL","PUT"], strike, expiration_date: date, quote_date: date, bid: float|None,
  ask: float|None, open_interest: int|None=None`, plus a `.mid` property. The data layer
  imports it locally / under `TYPE_CHECKING` (layering rule).
- `DailyBarSnapshot` (`src/prescient/data/models.py`): frozen, `ticker, trading_date: date,
  open/high/low/close: float|None, volume, vwap`.
- Assembler (`src/prescient/edge/data/assembler.py`) already derives the as-of trading day:
  `calendar_prior = report_date - timedelta(days=1)`, `visible =
  dataset.bars_as_of(ticker, as_of_date=calendar_prior)`, `as_of_date =
  visible[-1].trading_date`. `bars_as_of` returns bars `<= as_of_date` sorted ascending.
- Option loader (`src/prescient/edge/data/option_loader.py`) currently:
  `load_option_quotes_for_events(adapter, *, events, max_expiration_days)` calling
  `adapter.get_atm_option_quotes(...)` with `try/except -> continue`.
- Live readers live in `src/prescient/live_data/alpaca_readers.py`;
  `build_alpaca_sdk_readers(*, api_key_id, api_secret_key)` builds SDK clients inside the
  function (imports `OptionHistoricalDataClient`, `StockHistoricalDataClient`,
  `TradingClient`, requests). The historical reader will use
  `GetOptionContractsRequest(status="inactive", type=..., expiration_date_gte=...,
  expiration_date_lte=...)` and `OptionBarsRequest(symbol_or_symbols=[...], start, end,
  timeframe=TimeFrame.Day)`.
- Verified live (2026-06-05): contract objects expose `.symbol, .strike_price,
  .expiration_date, .open_interest`; option bar objects expose `.close, .open, .high,
  .low, .volume, .vwap, .timestamp` (`.timestamp.date()` gives the bar date).
- Tests in `tests/`, run `uv run pytest`. TDD, ruff line-length 100, ASCII comments.

## File structure

- Modify `src/prescient/data/alpaca_market.py` — add `HistoricalOptionRow` dataclass +
  `HistoricalOptionReader` alias + `get_historical_atm_straddle` method.
- Modify `src/prescient/live_data/alpaca_readers.py` — add
  `build_historical_option_reader`.
- Modify `src/prescient/edge/data/assembler.py` — add `as_of_price_for` helper.
- Modify `src/prescient/edge/data/option_loader.py` — rewire to historical straddle +
  `as_of_prices` arg.
- Modify `scripts/run_edge_backtest.py` — wire the historical reader; build the
  `as_of_prices` map; drop the KNOWN-LIMITATION docstring note.
- Tests: `tests/test_edge_data_historical_options.py` (new),
  `tests/test_edge_data_option_loader.py` (rewrite for new signature),
  `tests/test_edge_data_assembler.py` (add `as_of_price_for` test).

---

### Task 1: `HistoricalOptionRow` + `get_historical_atm_straddle` (pure adapter method)

**Files:**
- Modify: `src/prescient/data/alpaca_market.py`
- Test: `tests/test_edge_data_historical_options.py`

The method takes an injected `historical_option_reader` callable returning
`HistoricalOptionRow`s (contract metadata + the as-of close), filters to the expiration
window, picks the ATM strike nearest `underlying_price` among CALLs, pairs it with the
PUT at the same strike, and returns `[call_quote, put_quote]` priced `bid=ask=close`.
Returns `[]` if either leg is unavailable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_edge_data_historical_options.py
from __future__ import annotations

from datetime import date

from prescient.data.alpaca_market import (
    AlpacaMarketDataAdapter,
    HistoricalOptionRow,
)


def _row(symbol, strike, ot, close, exp=date(2024, 6, 28), oi=1000):
    return HistoricalOptionRow(
        contract_symbol=symbol,
        strike=strike,
        expiration_date=exp,
        option_type=ot,
        close=close,
        open_interest=oi,
    )


def _adapter(rows):
    def reader(*, underlying_symbol, as_of_date, earnings_date, max_expiration_date):
        return rows
    return AlpacaMarketDataAdapter(historical_option_reader=reader)


def test_picks_atm_pair_and_prices_at_close() -> None:
    rows = [
        _row("MU_C_138", 138.0, "CALL", 10.0),
        _row("MU_C_141", 141.0, "CALL", 9.08),   # nearest to 141.12
        _row("MU_P_141", 141.0, "PUT", 8.95),
        _row("MU_C_145", 145.0, "CALL", 6.0),
    ]
    adapter = _adapter(rows)
    quotes = adapter.get_historical_atm_straddle(
        underlying_symbol="mu", as_of_date=date(2024, 6, 25),
        underlying_price=141.12, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert len(quotes) == 2
    by_type = {q.option_type: q for q in quotes}
    assert by_type["CALL"].strike == 141.0
    assert by_type["PUT"].strike == 141.0
    # priced at close: bid == ask == close, so mid == close
    assert by_type["CALL"].bid == 9.08 and by_type["CALL"].ask == 9.08
    assert by_type["CALL"].mid == 9.08
    assert by_type["PUT"].mid == 8.95
    assert by_type["CALL"].quote_date == date(2024, 6, 25)
    assert by_type["CALL"].ticker == "MU"


def test_returns_empty_when_put_leg_missing() -> None:
    rows = [_row("MU_C_141", 141.0, "CALL", 9.08)]  # no PUT
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_returns_empty_when_no_contracts() -> None:
    quotes = _adapter([]).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_returns_empty_when_leg_close_missing() -> None:
    rows = [
        _row("MU_C_141", 141.0, "CALL", None),  # no close
        _row("MU_P_141", 141.0, "PUT", 8.95),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_filters_out_contracts_outside_expiration_window() -> None:
    rows = [
        _row("MU_C_141_late", 141.0, "CALL", 9.0, exp=date(2024, 9, 20)),  # too late
        _row("MU_P_141_late", 141.0, "PUT", 8.0, exp=date(2024, 9, 20)),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert quotes == []


def test_tie_break_prefers_lower_strike() -> None:
    # underlying exactly between 140 and 142 -> equidistant -> lower (140) wins
    rows = [
        _row("MU_C_140", 140.0, "CALL", 10.0),
        _row("MU_P_140", 140.0, "PUT", 9.0),
        _row("MU_C_142", 142.0, "CALL", 8.0),
        _row("MU_P_142", 142.0, "PUT", 11.0),
    ]
    quotes = _adapter(rows).get_historical_atm_straddle(
        underlying_symbol="MU", as_of_date=date(2024, 6, 25),
        underlying_price=141.0, earnings_date=date(2024, 6, 26),
        max_expiration_date=date(2024, 7, 10),
    )
    assert {q.strike for q in quotes} == {140.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_historical_options.py -v`
Expected: FAIL with `ImportError: cannot import name 'HistoricalOptionRow'`

- [ ] **Step 3: Write minimal implementation**

In `src/prescient/data/alpaca_market.py`: add the dataclass + alias near the existing
`OptionChainEntry` dataclass (top of file, after imports), and add the method to the
class after `get_atm_option_quotes`.

Add the dataclass and alias (place next to `OptionChainEntry`):

```python
@dataclass(frozen=True)
class HistoricalOptionRow:
    """A past option contract + its close on a specific as-of date (from option bars)."""

    contract_symbol: str
    strike: float
    expiration_date: date
    option_type: Literal["CALL", "PUT"]
    close: float | None
    open_interest: int | None = None


HistoricalOptionReader = Callable[..., list["HistoricalOptionRow"]]
```

Add `historical_option_reader` to `__init__` (keep existing params):

```python
    def __init__(
        self,
        *,
        option_chain_reader: OptionChainReader | None = None,
        daily_bars_reader: DailyBarsReader | None = None,
        historical_option_reader: "HistoricalOptionReader | None" = None,
        error_sink: ErrorSink | None = None,
    ) -> None:
        self._option_chain_reader = option_chain_reader
        self._daily_bars_reader = daily_bars_reader
        self._historical_option_reader = historical_option_reader
        self._errors: list[DataProviderError] = []
        self._error_sink = error_sink or self._errors.append
```

Add the method (after `get_atm_option_quotes`):

```python
    def get_historical_atm_straddle(
        self,
        *,
        underlying_symbol: str,
        as_of_date: date,
        underlying_price: float,
        earnings_date: date,
        max_expiration_date: date,
    ) -> list["OptionQuote"]:
        """Return the as-of ATM [call, put] straddle for a past earnings event, priced
        at each leg's bar close (history has no bid/ask; the spread cost is modeled in
        the P&L haircut, so close avoids double-counting). Returns [] on any missing
        piece (no contracts, only one leg, missing close) - skip, never guess. Strike
        is the one nearest underlying_price; ties resolve to the lower strike."""
        from prescient.edge.models import OptionQuote

        symbol = underlying_symbol.strip().upper()
        if self._historical_option_reader is None:
            self._record(
                DataProviderErrorType.PROVIDER_UNAVAILABLE,
                "Alpaca historical-option reader is not configured.",
                symbol=symbol,
            )
            return []
        try:
            rows = self._historical_option_reader(
                underlying_symbol=symbol,
                as_of_date=as_of_date,
                earnings_date=earnings_date,
                max_expiration_date=max_expiration_date,
            )
        except Exception as exc:  # transport/auth/subscription failure
            self._record(*_classify(exc), symbol=symbol)
            return []

        in_window = [
            row
            for row in rows
            if earnings_date <= row.expiration_date <= max_expiration_date
            and row.close is not None
        ]
        calls = [r for r in in_window if r.option_type == "CALL"]
        puts = [r for r in in_window if r.option_type == "PUT"]
        if not calls or not puts:
            return []

        # ATM strike: nearest to underlying_price among CALLs; ties -> lower strike.
        atm_strike = min(
            (r.strike for r in calls),
            key=lambda s: (abs(s - underlying_price), s),
        )
        call = next((r for r in calls if r.strike == atm_strike), None)
        put = next((r for r in puts if r.strike == atm_strike), None)
        if call is None or put is None:
            return []

        return [
            OptionQuote(
                ticker=symbol,
                option_type="CALL",
                strike=atm_strike,
                expiration_date=call.expiration_date,
                quote_date=as_of_date,
                bid=call.close,
                ask=call.close,
                open_interest=call.open_interest,
            ),
            OptionQuote(
                ticker=symbol,
                option_type="PUT",
                strike=atm_strike,
                expiration_date=put.expiration_date,
                quote_date=as_of_date,
                bid=put.close,
                ask=put.close,
                open_interest=put.open_interest,
            ),
        ]
```

Ensure `dataclass`, `date`, `Literal`, `Callable` are imported at the top (the file
already imports `dataclass`, `date`, `Literal`, `Callable` for `OptionChainEntry`; if
`Callable` is only imported under a specific name, reuse the existing import). Keep the
`from prescient.edge.models import OptionQuote` LOCAL to the method (layering). If a
`TYPE_CHECKING` import of `OptionQuote` already exists at the top, the return annotation
`list["OptionQuote"]` resolves; otherwise quote it as a string (already done).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_historical_options.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Confirm no regression + lint**

Run: `uv run pytest tests/ -k "alpaca or option" -q` (existing Alpaca/option tests still pass)
Run: `uv run ruff check src/prescient/data/alpaca_market.py tests/test_edge_data_historical_options.py`
Expected: green + clean.

- [ ] **Step 6: Commit**

```bash
git add src/prescient/data/alpaca_market.py tests/test_edge_data_historical_options.py
git commit -m "feat(edge-data): historical ATM straddle reader (pure, close-priced)"
```

---

### Task 2: `as_of_price_for` helper in the assembler

**Files:**
- Modify: `src/prescient/edge/data/assembler.py`
- Test: `tests/test_edge_data_assembler.py`

A small pure helper returning `(as_of_date, underlying_price)` for an event, reusing the
same last-trading-day anchor logic the assembler already applies. Used by the live script
to build the `as_of_prices` map for the option loader. The assembler's own internal logic
stays as-is (we add the helper and have the assembler not need it internally — it already
inlines the anchor; this helper is the reusable seam).

- [ ] **Step 1: Write the failing test (append to tests/test_edge_data_assembler.py)**

```python
def test_as_of_price_for_returns_prior_trading_day_and_close() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    bars = {
        "MU": [
            _bar("MU", date(2024, 6, 27), 98.0),
            _bar("MU", date(2024, 6, 28), 100.0),  # Friday: prior trading day to 07-01
            _bar("MU", date(2024, 7, 1), 103.0),
        ]
    }
    # report Monday 2024-07-01 -> calendar prior Sunday 06-30 -> last trading day 06-28
    result = as_of_price_for("MU", date(2024, 7, 1), bars)
    assert result == (date(2024, 6, 28), 100.0)


def test_as_of_price_for_none_when_no_prior_bar() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    assert as_of_price_for("MU", date(2024, 7, 1), {}) is None


def test_as_of_price_for_none_when_close_missing() -> None:
    from prescient.edge.data.assembler import as_of_price_for

    bars = {"MU": [_bar("MU", date(2024, 6, 28), None)]}
    assert as_of_price_for("MU", date(2024, 7, 1), bars) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_assembler.py -k as_of_price_for -v`
Expected: FAIL with `ImportError: cannot import name 'as_of_price_for'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/prescient/edge/data/assembler.py` (module-level function, above
`assemble_edge_dataset`):

```python
def as_of_price_for(
    ticker: str,
    report_date: date,
    bars: dict[str, list[DailyBarSnapshot]],
) -> tuple[date, float] | None:
    """The (as_of_date, underlying_close) for an event: the last trading day on/before
    report_date - 1 calendar day, and its close. Returns None when no prior bar exists
    or the close is missing. Single source of truth for the as-of price (used to pick
    the ATM strike and matching the EventContext's underlying price)."""
    dataset = PointInTimeDataset(bars=bars, option_quotes={})
    calendar_prior = report_date - timedelta(days=1)
    visible = dataset.bars_as_of(ticker, as_of_date=calendar_prior)
    if not visible:
        return None
    last = visible[-1]
    if last.close is None:
        return None
    return last.trading_date, last.close
```

Add `from datetime import date, timedelta` (the file currently imports only `timedelta`
from datetime — update that import line to `from datetime import date, timedelta`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_assembler.py -v`
Expected: PASS (all assembler tests, incl. 3 new).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/prescient/edge/data/assembler.py tests/test_edge_data_assembler.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/prescient/edge/data/assembler.py tests/test_edge_data_assembler.py
git commit -m "feat(edge-data): as_of_price_for helper (single source of as-of price)"
```

---

### Task 3: Rewire option loader to the historical straddle

**Files:**
- Modify: `src/prescient/edge/data/option_loader.py`
- Test: `tests/test_edge_data_option_loader.py` (rewrite)

New signature takes `as_of_prices: dict[tuple[str, date], tuple[date, float]]` keyed by
`(ticker, report_date)`. For each event with a known as-of price, call
`get_historical_atm_straddle`. Skip-not-guess retained.

- [ ] **Step 1: Rewrite `tests/test_edge_data_option_loader.py`**

```python
from __future__ import annotations

from datetime import date

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


class FakeHistAdapter:
    def __init__(self):
        self.calls = []

    def get_historical_atm_straddle(self, *, underlying_symbol, as_of_date,
                                    underlying_price, earnings_date, max_expiration_date):
        self.calls.append({
            "symbol": underlying_symbol, "as_of_date": as_of_date,
            "underlying_price": underlying_price, "earnings_date": earnings_date,
            "max_expiration_date": max_expiration_date,
        })
        return [
            OptionQuote(ticker=underlying_symbol, option_type="CALL", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=as_of_date,
                        bid=9.0, ask=9.0),
            OptionQuote(ticker=underlying_symbol, option_type="PUT", strike=100.0,
                        expiration_date=date(2024, 6, 28), quote_date=as_of_date,
                        bid=8.0, ask=8.0),
        ]


def test_loads_straddle_per_event_threading_as_of_price() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    as_of_prices = {("MU", date(2024, 6, 26)): (date(2024, 6, 25), 141.12)}
    adapter = FakeHistAdapter()
    out = load_option_quotes_for_events(
        adapter, events=events, as_of_prices=as_of_prices, max_expiration_days=14,
    )
    assert len(out["MU"]) == 2
    call = adapter.calls[0]
    assert call["as_of_date"] == date(2024, 6, 25)
    assert call["underlying_price"] == 141.12
    assert call["max_expiration_date"] == date(2024, 7, 10)  # report + 14d


def test_skips_event_without_as_of_price() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    events = [EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26))]
    adapter = FakeHistAdapter()
    out = load_option_quotes_for_events(
        adapter, events=events, as_of_prices={}, max_expiration_days=14,
    )
    assert out == {}
    assert adapter.calls == []


def test_continues_when_one_event_errors() -> None:
    from prescient.edge.data.option_loader import load_option_quotes_for_events

    class Flaky(FakeHistAdapter):
        def get_historical_atm_straddle(self, **kwargs):
            if kwargs["underlying_symbol"] == "BAD":
                raise RuntimeError("boom")
            return super().get_historical_atm_straddle(**kwargs)

    events = [
        EarningsAnnouncement(ticker="BAD", report_date=date(2024, 6, 26)),
        EarningsAnnouncement(ticker="MU", report_date=date(2024, 6, 26)),
    ]
    as_of_prices = {
        ("BAD", date(2024, 6, 26)): (date(2024, 6, 25), 50.0),
        ("MU", date(2024, 6, 26)): (date(2024, 6, 25), 141.0),
    }
    out = load_option_quotes_for_events(
        Flaky(), events=events, as_of_prices=as_of_prices, max_expiration_days=14,
    )
    assert "MU" in out and "BAD" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_edge_data_option_loader.py -v`
Expected: FAIL (signature mismatch / old code calls `get_atm_option_quotes`).

- [ ] **Step 3: Rewrite `src/prescient/edge/data/option_loader.py`**

```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

from prescient.edge.data.models import EarningsAnnouncement
from prescient.edge.models import OptionQuote


def load_option_quotes_for_events(
    adapter: Any,
    *,
    events: Sequence[EarningsAnnouncement],
    as_of_prices: dict[tuple[str, date], tuple[date, float]],
    max_expiration_days: int,
) -> dict[str, list[OptionQuote]]:
    """Fetch the as-of ATM straddle per event via the historical reader; accumulate per
    ticker. Events without a known as-of price are skipped; a failed fetch is skipped
    (skip-not-guess), never zero-filled."""
    out: dict[str, list[OptionQuote]] = {}
    for event in events:
        key = (event.ticker, event.report_date)
        as_of = as_of_prices.get(key)
        if as_of is None:
            continue
        as_of_date, underlying_price = as_of
        max_exp = event.report_date + timedelta(days=max_expiration_days)
        try:
            quotes = adapter.get_historical_atm_straddle(
                underlying_symbol=event.ticker,
                as_of_date=as_of_date,
                underlying_price=underlying_price,
                earnings_date=event.report_date,
                max_expiration_date=max_exp,
            )
        except Exception:  # noqa: BLE001  # intentional skip-not-guess
            continue
        if quotes:
            out.setdefault(event.ticker, []).extend(quotes)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_edge_data_option_loader.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/prescient/edge/data/option_loader.py tests/test_edge_data_option_loader.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/prescient/edge/data/option_loader.py tests/test_edge_data_option_loader.py
git commit -m "feat(edge-data): rewire option loader to historical straddle + as-of price"
```

---

### Task 4: SDK historical-option reader

**Files:**
- Modify: `src/prescient/live_data/alpaca_readers.py`
- Test: none (SDK-bound, needs keys; verified by import/parse + live smoke run).

Adds `build_historical_option_reader(*, api_key_id, api_secret_key) -> HistoricalOptionReader`
returning a callable that lists expired contracts (both types, expiration window) and
batch-fetches historical daily bars, emitting `HistoricalOptionRow`s with the as-of close.

- [ ] **Step 1: Add the function**

Append to `src/prescient/live_data/alpaca_readers.py`:

```python
def build_historical_option_reader(
    *, api_key_id: str, api_secret_key: str
) -> HistoricalOptionReader:
    """Build a live reader callable for as-of historical option straddles (read-only).

    Lists EXPIRED contracts (both CALL and PUT) in the expiration window, then batch
    fetches daily option bars and takes the bar on/just-before as_of_date for each
    contract, returning normalized HistoricalOptionRow rows (close from the bar)."""
    from datetime import datetime, timedelta

    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest

    option_data = OptionHistoricalDataClient(api_key_id, api_secret_key)
    trading = TradingClient(api_key_id, api_secret_key, paper=True)

    def historical_option_reader(
        *, underlying_symbol, as_of_date, earnings_date, max_expiration_date
    ) -> list[HistoricalOptionRow]:
        contracts: list[Any] = []
        for opt_type in ("call", "put"):
            resp = trading.get_option_contracts(
                GetOptionContractsRequest(
                    underlying_symbols=[underlying_symbol],
                    status="inactive",
                    type=opt_type,
                    expiration_date_gte=earnings_date,
                    expiration_date_lte=max_expiration_date,
                    limit=1000,
                )
            )
            contracts.extend(getattr(resp, "option_contracts", []) or [])
        if not contracts:
            return []

        symbol_meta = {
            c.symbol: (
                float(c.strike_price),
                c.expiration_date,
                "CALL" if str(c.type).lower().endswith("call") else "PUT",
                int(c.open_interest) if c.open_interest is not None else None,
            )
            for c in contracts
        }

        start = datetime(as_of_date.year, as_of_date.month, as_of_date.day) - timedelta(days=4)
        end = datetime(as_of_date.year, as_of_date.month, as_of_date.day) + timedelta(days=1)
        bars_resp = option_data.get_option_bars(
            OptionBarsRequest(
                symbol_or_symbols=list(symbol_meta.keys()),
                start=start,
                end=end,
                timeframe=TimeFrame.Day,
            )
        )
        bars_by_symbol = getattr(bars_resp, "data", {}) or {}

        rows: list[HistoricalOptionRow] = []
        for symbol, (strike, expiration, opt_type, open_interest) in symbol_meta.items():
            bars = bars_by_symbol.get(symbol, [])
            as_of_bar = None
            for bar in bars:
                if bar.timestamp.date() <= as_of_date:
                    as_of_bar = bar
            rows.append(
                HistoricalOptionRow(
                    contract_symbol=symbol,
                    strike=strike,
                    expiration_date=expiration,
                    option_type=opt_type,
                    close=getattr(as_of_bar, "close", None),
                    open_interest=open_interest,
                )
            )
        return rows

    return historical_option_reader
```

Update the imports at the top of `alpaca_readers.py` to also import the new names from
the data adapter (alongside the existing `from prescient.data.alpaca_market import (...)`):
add `HistoricalOptionRow` and `HistoricalOptionReader` to that import block. Add
`from typing import Any` if not present.

- [ ] **Step 2: Verify it parses + imports (no live call)**

Run: `uv run python -c "import importlib.util,sys; s=importlib.util.spec_from_file_location('r','src/prescient/live_data/alpaca_readers.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('imports ok', hasattr(m,'build_historical_option_reader'))"`
Expected: `imports ok True`

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/prescient/live_data/alpaca_readers.py`
Expected: clean (keep line-length <=100; the `Any` rows annotation is fine).

- [ ] **Step 4: Commit**

```bash
git add src/prescient/live_data/alpaca_readers.py
git commit -m "feat(edge-data): SDK historical-option reader (expired contracts + bars)"
```

---

### Task 5: Wire the live script + drop the KNOWN-LIMITATION note

**Files:**
- Modify: `scripts/run_edge_backtest.py`
- Test: none (live script; verified by parse/import + `--help`).

Build the historical reader, attach it to the adapter, build the `as_of_prices` map from
bars via `as_of_price_for`, call the rewired loader, and remove the KNOWN-LIMITATION
docstring block.

- [ ] **Step 1: Update imports + adapter construction + option loading**

In `scripts/run_edge_backtest.py`:

1. Remove the entire `KNOWN LIMITATION (...)` paragraph from the module docstring
   (keep the rest of the docstring).

2. Add to the imports:
```python
from prescient.edge.data.assembler import as_of_price_for, assemble_edge_dataset
from prescient.live_data.alpaca_readers import (
    build_alpaca_sdk_readers,
    build_historical_option_reader,
)
```
(Replace the existing `from prescient.edge.data.assembler import assemble_edge_dataset`
and the existing `from prescient.live_data.alpaca_readers import build_alpaca_sdk_readers`
lines with these.)

3. After building `alpaca` and `bars`, and after computing `target_events`, replace the
   option-loading block. The OLD block is:
```python
    option_quotes = load_option_quotes_for_events(
        alpaca, events=target_events, max_expiration_days=_MAX_EXPIRATION_DAYS
    )
    print(f"Tickers with option quotes: {len(option_quotes)}")
```
   Replace with:
```python
    hist_reader = build_historical_option_reader(
        api_key_id=alpaca_id, api_secret_key=alpaca_secret
    )
    hist_adapter = AlpacaMarketDataAdapter(historical_option_reader=hist_reader)

    as_of_prices: dict[tuple[str, date], tuple[date, float]] = {}
    for event in target_events:
        priced = as_of_price_for(event.ticker, event.report_date, bars)
        if priced is not None:
            as_of_prices[(event.ticker, event.report_date)] = priced

    option_quotes = load_option_quotes_for_events(
        hist_adapter,
        events=target_events,
        as_of_prices=as_of_prices,
        max_expiration_days=_MAX_EXPIRATION_DAYS,
    )
    print(f"Tickers with option quotes: {len(option_quotes)}")
```

Ensure `AlpacaMarketDataAdapter` and `date` are already imported (the script imports
`AlpacaMarketDataAdapter` and `from datetime import date, timedelta` already; verify).

- [ ] **Step 2: Verify parse + imports + --help**

Run: `uv run python -c "import ast; ast.parse(open('scripts/run_edge_backtest.py').read()); print('parses ok')"`
Run: `uv run python -c "import importlib.util; s=importlib.util.spec_from_file_location('r','scripts/run_edge_backtest.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('imports ok')"`
Run: `uv run python scripts/run_edge_backtest.py --help`
Expected: `parses ok`, `imports ok`, and the argparse help text.

- [ ] **Step 3: Confirm KNOWN-LIMITATION note is gone**

Run: `grep -c "KNOWN LIMITATION" scripts/run_edge_backtest.py`
Expected: `0`

- [ ] **Step 4: Lint**

Run: `uv run ruff check scripts/run_edge_backtest.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_edge_backtest.py
git commit -m "feat(edge-data): wire historical straddle reader into live backtest script"
```

---

### Task 6: Full-suite green + lint gate

**Files:** none (verification).

- [ ] **Step 1: Edge-data + alpaca suites**

Run: `uv run pytest tests/ -k "edge_data or alpaca or option" -q`
Expected: all pass.

- [ ] **Step 2: Full suite**

Run: `uv run pytest -q`
Expected: all pass (only the rewired option-loader test changed; no scoring changes).

- [ ] **Step 3: Lint the whole touched surface**

Run: `uv run ruff check src/prescient/data/alpaca_market.py src/prescient/live_data/alpaca_readers.py src/prescient/edge/data scripts/run_edge_backtest.py tests`
Expected: clean.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A -- src/prescient tests scripts
git commit -m "chore(edge-data): lint + full-suite green for historical options" || echo "nothing to commit"
```

(Note: `git add -A -- src/prescient tests scripts` scopes to our dirs only, never staging
AGENTS.md or supabase/migrations.)

---

## Self-Review

**1. Spec coverage:**
- Pure `get_historical_atm_straddle` (injected reader, close-priced, ATM nearest, []-on-miss,
  lower-strike tie-break) → Task 1. ✓
- SDK `build_historical_option_reader` (expired contracts both types + batched bars) → Task 4. ✓
- `as_of_price_for` single-source-of-truth helper → Task 2. ✓
- Option loader rewire with `as_of_prices` threading → Task 3. ✓
- Live script wiring + drop KNOWN-LIMITATION → Task 5. ✓
- Layering (data layer SDK-free; local OptionQuote import) → Task 1 (local import). ✓
- Skip-not-guess (no contracts / one leg / missing close / transport error) → Task 1 + Task 3. ✓
- Leg priced at close, bid=ask=close → Task 1 (+ test asserts mid==close). ✓
- Caching: the existing JsonFileCache is used for EARNINGS today; option straddle caching
  is NOT added in this plan — the spec lists it as a commitment. NOTE: deferred to a
  follow-up to keep this plan focused on making the metric computable; flagged here, not
  silently dropped. The `--limit` smoke guard already bounds the first run's cost.
- Frozen scoring untouched → only data/live_data/edge.data/scripts touched. ✓
- Success criterion (option columns populated on a live --limit run) → achievable after
  Task 5; verified live by the user (needs keys), not in the suite. ✓

**2. Placeholder scan:** No TBD/TODO; every code step is complete. The straddle-cache
deferral is explicitly flagged above (not a silent omission).

**3. Type consistency:**
- `HistoricalOptionRow(contract_symbol, strike, expiration_date, option_type, close,
  open_interest)` defined Task 1, produced by the reader in Task 4, consumed by the
  adapter method in Task 1 — fields match.
- `get_historical_atm_straddle(*, underlying_symbol, as_of_date, underlying_price,
  earnings_date, max_expiration_date)` consistent across Tasks 1, 3 (loader call), 5.
- `load_option_quotes_for_events(adapter, *, events, as_of_prices, max_expiration_days)`
  consistent Tasks 3, 5.
- `as_of_price_for(ticker, report_date, bars) -> tuple[date, float] | None` consistent
  Tasks 2, 5.
- `as_of_prices` key `(ticker, report_date)` and value `(as_of_date, underlying_price)`
  consistent Tasks 3, 5.

## Notes / deferred (flagged, not dropped)

- **Straddle disk-caching** (spec commitment #5): deferred to a follow-up. The earnings
  cache already exists; option-straddle caching by `(ticker, as_of_date)` is a clean add
  but not required to make the metric computable. `--limit` bounds the first run. Add it
  if the full ~200-event run proves too slow/rate-limited.
- The SDK reader takes the bar on/just-before `as_of_date`; if Alpaca returns no bar in
  the small window, `close` is None → leg dropped → straddle `[]` (skip-not-guess).
