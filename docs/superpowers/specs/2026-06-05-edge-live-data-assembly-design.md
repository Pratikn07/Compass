# Edge Live-Data Assembly — Design

**Date:** 2026-06-05
**Status:** Design (awaiting review)
**Sub-project:** 2 of the single-name earnings-prediction rethink — the data layer that
feeds the (already-built, frozen) edge backtest harness so the first REAL backtest can run.

---

## Why this exists

The edge backtest harness (`prescient.edge`, sub-project 1, complete) is built and
green but runs on hand-constructed `PointInTimeDataset`s in tests. Two gaps stop a real
run:

1. Nothing fills `PointInTimeDataset` (`bars` + `option_quotes`) from live data.
2. Nothing produces the historical **event spine** (which names reported, on what date,
   with what EPS estimate/actual) or the thesis's **peer signals**
   (`peer_eps_surprises`, `peer_stock_reactions`), which are empty today.

This sub-project builds that assembly layer. It does NOT change scoring/survival logic
(frozen) and does NOT trade.

### Live data-source findings (probed 2026-06-05, free tiers)

| Data piece | Source | Free-tier reality |
|---|---|---|
| Stock daily bars (~10yr) | Alpaca | Available (2016 to now) |
| Historical option straddles | Alpaca | Available (verified MU 2024 ATM straddle) |
| EPS actual vs estimate (last ~4q) | Finnhub | Only last ~4 quarters, keyed by fiscal-period |
| Historical earnings DATES | Finnhub | Empty for any past window |
| Historical earnings calendar (date-bounded) | FMP | 402 Payment Required (paid feature) |
| **Historical earnings dates + EPS est/actual** | **Alpha Vantage `EARNINGS`** | **FREE, ~30yr depth** |

**Conclusion:** the historical earnings **spine** IS available free after all — the
Alpha Vantage `EARNINGS` endpoint returns, in a single per-ticker call, decades of
`reportedDate` (the announcement date — our anchor), `estimatedEPS`, `reportedEPS`,
`surprise`, `surprisePercentage`, and `reportTime` (BMO/AMC). Verified live on the
public `demo` key (IBM: 121 quarters back to 1996). **No paid subscription is needed**
(FMP-paid was the earlier plan; the Alpha Vantage probe made it unnecessary). Prices +
options stay free on Alpaca. The whole sub-project is $0.

The only cost is Alpha Vantage's free-tier **rate limit** (historically ~25 req/day),
which is a non-issue here: one request per ticker returns ALL history, and the
fetch-once cache means we never re-hit it (25 names = one day's budget, cached forever).

---

## Scope

**In scope:** assemble `(list[EventContext], PointInTimeDataset)` from Alpha Vantage
(free) earnings history + Alpaca bars/options, compute peer signals, and a single live
command that runs the existing harness and prints the scorecard.

**Out of scope:** any change to `prescient.edge` scoring/survival modules (frozen); live
or paper trading; news/sentiment/revision collectors (later sub-projects); a UI.

## Governing commitments

1. **Swappable earnings source.** Assembly depends on an `EarningsHistoryProvider`
   interface, not on any one vendor. **Alpha Vantage `EARNINGS` (free) is the
   implementation this sub-project ships**; the interface keeps a vendor swap (e.g. to a
   paid source) a one-file change. (Direct consequence of today's probes: don't weld to
   one vendor — and verify before paying. The verify step turned a planned paid
   dependency into a free one.)
2. **No-lookahead preserved.** Inputs use only data `<= as_of_date`; the realized move is
   the only allowed look-forward (already isolated in `compute_realized_move`). The peer
   filter (below) is the key new guard.
3. **Skip-not-guess.** Missing earnings record -> event dropped (logged). Missing straddle
   leg -> not_evaluable. Missing peer bars -> that peer omitted, never zero-filled.
4. **Fetch-once-and-cache.** Paid/rate-limited calls are cached on disk (normalized, no
   secrets) so re-runs don't re-hit the APIs.
5. **No live calls in the test suite.** Every unit is tested with injected fakes; the
   live command's pure pieces are all unit-tested.
6. **Propose-only.** Nothing here places, sizes, authorizes, or recommends a trade.

---

## Components (each small, single-purpose, independently testable)

All under a new subpackage `src/prescient/edge/data/` (separate from the frozen scoring
core).

### 1. `earnings_history.py`
- `EarningsAnnouncement` (frozen model): `ticker`, `report_date: date`,
  `report_time: ReportTime`, `eps_estimate: float | None`, `eps_actual: float | None`,
  `surprise_pct: float | None` (Alpha Vantage gives this directly).
- `EarningsHistoryProvider` (Protocol):
  `get_earnings_history(*, tickers, start, end) -> list[EarningsAnnouncement]`.
- `AlphaVantageEarningsHistoryAdapter` (the impl this ships): one `EARNINGS` call per
  ticker (`function=EARNINGS&symbol=…&apikey=…`), reads `quarterlyEarnings[]`, maps
  `reportedDate -> report_date`, `estimatedEPS -> eps_estimate`,
  `reportedEPS -> eps_actual`, `surprisePercentage -> surprise_pct`,
  `reportTime -> report_time` (BMO/AMC/UNKNOWN), filters to `[start, end]`, returns
  secret-safe structured errors (incl. the AV rate-limit "Note"/"Information" message ->
  a RATE_LIMITED error). Lives alongside the existing `AlphaVantageNewsSentimentAdapter`
  in `src/prescient/data/alpha_vantage.py` (reuse its `SyncHttpClient` transport +
  `_get` error pattern) OR in the new `edge/data/earnings_history.py` wrapping that
  transport — implementation chooses the lower-duplication path. Injected HTTP transport;
  no live calls in tests.

### 2. `bars_loader.py`
- `HistoricalBarsLoader.load(*, tickers, start, end) -> dict[str, list[DailyBarSnapshot]]`
  wrapping the existing Alpaca daily-bars reader, batched multi-symbol.

### 3. `option_loader.py`
- `HistoricalOptionLoader.load_for_events(*, events, max_expiration_days)
  -> dict[str, list[OptionQuote]]`: for each event, calls the existing
  `AlpacaMarketDataAdapter.get_atm_option_quotes` for the pre-earnings window; accumulates
  per-ticker quotes. One chain pull per event (the expensive call), cached.

### 4. `peer_signals.py` (pure)
- `build_peer_signals(*, target, announcements, bars, peer_window_days)
  -> tuple[dict[str, float], dict[str, float]]` returning
  `(peer_eps_surprises, peer_stock_reactions)`.
  - A peer counts ONLY if `peer.report_date < target.as_of_date` AND within the trailing
    `peer_window_days` (default 21) — mirrors the candidate engine's rule. This is the
    central no-lookahead guard of this layer.
  - `peer_eps_surprises[peer]` = percent EPS surprise. Prefer the provider's
    `surprise_pct` when present (Alpha Vantage supplies it directly); otherwise compute
    `((eps_actual - eps_estimate) / |eps_estimate|) * 100` when both present.
  - `peer_stock_reactions[peer]` = percent move from the close the trading day BEFORE the
    peer's report to the close the trading day AFTER (close-before -> close-after),
    computed from `bars`. Peer omitted if either close is missing.

### 5. `assembler.py`
- `DatasetAssembler.assemble(...) -> AssembledEdgeDataset` (holds
  `event_contexts: list[EventContext]` and `dataset: PointInTimeDataset`, plus a
  coverage/error summary). Orchestrates 1-3, builds the dataset, derives `as_of_date`
  per event (`report_date - 1 day`, loader walks back to the real prior close), calls the
  existing `build_event_context`, attaches peer signals from #4, and drops events with no
  as-of price (logged).

### 6. `cache.py`
- Simple on-disk fetch-once cache (normalized JSON, no secrets) keyed by source +
  parameters, so earnings/options/bars are fetched once and reused across runs.

### Live command
- `scripts/run_edge_backtest.py`: assembles the dataset (with `--limit N` to cap events
  for a cheap smoke test), runs `run_edge_backtest`, and prints the side-by-side scorecard
  (thesis vs coin-flip vs always-up) with survival verdict, sample-size label, and a
  one-line coverage summary (e.g. "187/200 events evaluable; 13 dropped: 9 missing
  straddle, 4 missing earnings record"). Not in the test suite (needs keys).

## Data flow (one direction)

```
EarningsHistoryProvider (Alpha Vantage, free) ─┐
HistoricalBarsLoader (Alpaca)                   ├─> DatasetAssembler ─> (EventContexts, PointInTimeDataset)
HistoricalOptionLoader (Alpaca)                 ┘        │                         │
PeerSignalBuilder (pure, derived) <─────────────────────┘                         v
                                                          existing run_edge_backtest -> scorecards
```

Nothing here reaches into scoring; it only produces inputs.

## No-lookahead discipline (the correctness core)

- `as_of_date` = last trading day strictly before `report_date` (pass `report_date - 1`;
  `_latest_close` already tolerates holidays).
- Inputs (underlying price, ATM straddle, peer signals) use only data `<= as_of_date`.
- Realized move uses post-report bars — the only allowed look-forward, already isolated.
- **Peer filter:** a peer counts only if `peer.report_date < target.as_of_date`. Never
  feed a peer whose report came at/after the target's anchor.
- Option quotes must be `<= as_of_date`; `option_quotes_as_of` filters later ones
  (defense in depth).

## Cost control

- Earnings history: one Alpha Vantage `EARNINGS` call per ticker (returns ALL history),
  cached to disk and reused across runs. AV free tier is rate-limited (~25 req/day) —
  25 names fits one day's budget, and the cache means we fetch each ticker once, ever.
- Bars: one batched multi-symbol Alpaca call over the full window.
- Options: one chain pull per event (the expensive call), cached by (ticker, as_of_date).
- `--limit N` guard for a ~20-event smoke test before the full ~200.
- Adapters return secret-safe structured errors; the assembler collects them and reports
  per-source failure counts instead of crashing.

## Error handling

- Missing earnings record -> event dropped (counted in coverage summary).
- Missing straddle leg / option data -> EventContext built but scores not_evaluable.
- Missing peer bars -> that peer omitted from signals, never zero-filled.
- API failure -> secret-safe structured error collected; run continues with whatever
  assembled successfully; the loud sample-size verdict reflects real coverage.

## Testing

TDD, injected fakes, no live calls in the suite:
- `AlphaVantageEarningsHistoryAdapter`: feed the live JSON shape (`quarterlyEarnings[]`
  with `reportedDate`/`estimatedEPS`/`reportedEPS`/`surprisePercentage`/`reportTime`);
  assert normalized announcements, date-window filtering, BMO/AMC mapping, and
  secret-safe errors on the AV rate-limit "Note"/"Information" message (-> RATE_LIMITED)
  and on timeout.
- `HistoricalBarsLoader` / `HistoricalOptionLoader`: fake readers; assert batching and
  per-ticker accumulation.
- `PeerSignalBuilder`: the critical test — a peer reporting at/after the target's
  `as_of_date` is EXCLUDED; one reporting before, in-window, is INCLUDED with correct
  close-to-close reaction and EPS-surprise percent; missing-bar peer omitted.
- `DatasetAssembler`: end-to-end with fakes -> EventContexts whose every input is
  `<= as_of_date` (assembly-level lookahead guard) + correct coverage summary.
- `cache.py`: round-trips normalized data, no secrets persisted.

## File layout

```
src/prescient/edge/data/
  __init__.py
  earnings_history.py     # EarningsAnnouncement + EarningsHistoryProvider + AlphaVantageEarningsHistoryAdapter
  bars_loader.py
  option_loader.py
  peer_signals.py
  assembler.py
  cache.py
scripts/run_edge_backtest.py
tests/test_edge_data_*.py
```

Requires a free `ALPHAVANTAGE_API_KEY` in `.env` for the live run only (the public
`demo` key works for IBM only; tests use fakes and need no key).

The frozen scoring modules (`scorer`, `runner`, `scorecard`, `strategy`, `loader`,
`option_pnl`, `implied_move`, `realized_move`, `models`) are NOT modified.

## Success criteria

- `scripts/run_edge_backtest.py --limit 20` runs end-to-end against live keys and prints
  a scorecard with a coverage summary, using cached data on re-run.
- Peer-filter no-lookahead test passes (peer at/after target as-of excluded).
- All assembly units are green with fakes; the frozen scoring suite still passes.
- The first real survived/dead verdict for the thesis vs baselines is produced, with an
  honest sample-size label — evidence, not assumption.

## Known limitation found in implementation (blocks live option metrics)

The existing live Alpaca option reader (`prescient.live_data.alpaca_readers`) fetches
only the CURRENT, CALL-only active chain. The implied move requires an as-of-date ATM
CALL+PUT straddle, so with this reader every event scores `not_evaluable /
missing_implied_move` and the option scorecard is empty. The stock-side spine (earnings
dates, bars, peer signals) and the assembly pipeline are real and tested; only the
option-quote source is insufficient for a meaningful first run. Resolving it needs a
**historical-options reader** (Alpaca `get_option_bars` per expired contract, both
CALL and PUT, stamped with the true historical quote date) — the Alpaca probe on
2026-06-05 confirmed that data exists on the free tier. This is the next sub-project.

## Explicitly deferred (later sub-projects)

- Historical-options reader (CALL+PUT, true as-of quote dates) — required before the
  option/implied-move metrics are meaningful (see Known limitation above).

- News / sentiment / analyst-revision collectors.
- The blending prediction engine and selectivity gate.
- Dashboard.
- Forward paper-trading (only if the backtest survives).
