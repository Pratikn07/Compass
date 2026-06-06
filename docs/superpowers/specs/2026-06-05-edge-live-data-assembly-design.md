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
| EPS actual vs estimate | Finnhub | Only last ~4 quarters, keyed by fiscal-period |
| Historical earnings DATES | Finnhub | Empty for any past window |
| Historical earnings calendar (date-bounded) | FMP | 402 Payment Required (paid feature) |

**Conclusion:** prices + options are free and sufficient; the historical earnings
**spine** is not available free. Decision (owner): use a **cheap paid earnings-history
source**, targeting **FMP's paid tier first** (key + adapter + endpoint shape already
proven), behind a swappable interface.

---

## Scope

**In scope:** assemble `(list[EventContext], PointInTimeDataset)` from FMP-paid earnings
history + Alpaca bars/options, compute peer signals, and a single live command that runs
the existing harness and prints the scorecard.

**Out of scope:** any change to `prescient.edge` scoring/survival modules (frozen); live
or paper trading; news/sentiment/revision collectors (later sub-projects); a UI.

## Governing commitments

1. **Swappable earnings source.** Assembly depends on an `EarningsHistoryProvider`
   interface, not on FMP. FMP-paid is the first implementation; swapping vendors must
   not touch assembly. (Direct consequence of today's probe: don't weld to one vendor.)
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
  `report_time: ReportTime`, `eps_estimate: float | None`, `eps_actual: float | None`.
- `EarningsHistoryProvider` (Protocol):
  `get_earnings_history(*, tickers, start, end) -> list[EarningsAnnouncement]`.
- `FmpEarningsHistoryAdapter` (first impl): calls FMP's date-bounded earnings endpoint
  (`/stable/earnings-calendar` with `from`/`to` on the paid tier), normalizes the shape
  observed live (`date`, `epsEstimated`, `epsActual`), filters to requested tickers,
  returns secret-safe structured errors on failure. Injected HTTP transport.

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
  - `peer_eps_surprises[peer]` = percent EPS surprise =
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
EarningsHistoryProvider (FMP-paid)  ─┐
HistoricalBarsLoader (Alpaca)        ├─> DatasetAssembler ─> (EventContexts, PointInTimeDataset)
HistoricalOptionLoader (Alpaca)      ┘        │                         │
PeerSignalBuilder (pure, derived) <──────────┘                         v
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

- Earnings history: one date-ranged sweep, cached to disk; reused across runs.
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
- `FmpEarningsHistoryAdapter`: feed the live JSON shape (`date`/`epsEstimated`/
  `epsActual`); assert normalized announcements + secret-safe errors on 402/timeout.
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
  earnings_history.py
  bars_loader.py
  option_loader.py
  peer_signals.py
  assembler.py
  cache.py
scripts/run_edge_backtest.py
tests/test_edge_data_*.py
```

The frozen scoring modules (`scorer`, `runner`, `scorecard`, `strategy`, `loader`,
`option_pnl`, `implied_move`, `realized_move`, `models`) are NOT modified.

## Success criteria

- `scripts/run_edge_backtest.py --limit 20` runs end-to-end against live keys and prints
  a scorecard with a coverage summary, using cached data on re-run.
- Peer-filter no-lookahead test passes (peer at/after target as-of excluded).
- All assembly units are green with fakes; the frozen scoring suite still passes.
- The first real survived/dead verdict for the thesis vs baselines is produced, with an
  honest sample-size label — evidence, not assumption.

## Explicitly deferred (later sub-projects)

- News / sentiment / analyst-revision collectors.
- The blending prediction engine and selectivity gate.
- Dashboard.
- Forward paper-trading (only if the backtest survives).
