# Historical-Options Reader — Design

**Date:** 2026-06-05
**Status:** Design (awaiting review)
**Sub-project:** 3 of the single-name earnings-prediction rethink — the last piece before
a meaningful first backtest verdict (makes the implied-move metric computable).

---

## Why this exists

The edge harness (sub-project 1) scores predictions against the options-implied move.
The live-data assembly (sub-project 2) wired earnings + bars + the *current* Alpaca
option chain — but that chain is CALL-only and current-snapshot, so the implied move was
uncomputable and every event scored `not_evaluable / missing_implied_move`. This
sub-project adds a **historical-options reader** that fetches the as-of-date ATM CALL+PUT
straddle for each past earnings event, so the implied move (and thus the whole option
axis of the backtest) finally works.

### Verified live data path (probed 2026-06-05, free/paper Alpaca tier)

For MU's 2024-06-26 report, as_of 2024-06-25:
- Underlying MU close as_of = $141.12 → ATM strike $141.
- Expired contracts listable: `status="inactive"`, `type` in {call, put},
  `expiration_date_gte/lte`, fields incl. `symbol, strike_price, expiration_date,
  open_interest`.
- `get_option_bars` returns a daily bar on the exact as_of date for BOTH legs:
  call close $9.08, put close $8.95 → straddle $18.03 → implied move ~12.8%. Liquid
  (volume 1865 / 1685).
- `get_option_bars` accepts multiple symbols in one call (batching confirmed).

## Scope

**In scope:** fetch the as-of ATM CALL+PUT straddle for a past event and return it as two
`OptionQuote`s; wire it into the option loader + assembler; enable the live script's
option metrics.

**Out of scope:** changes to scoring/survival logic (frozen); the current-chain reader
(`get_atm_option_quotes`) stays as a sibling, untouched; news/sentiment; live/paper
trading.

## Governing commitments

1. **Leg price = bar close.** History gives OHLC, not bid/ask. Each leg's `OptionQuote`
   is priced `bid = ask = close`, so the implied-move mid equals the real closing price.
   The bid/ask spread cost is NOT lost — it is already modeled in the P&L cost-haircut;
   pricing the leg at close avoids double-counting cost.
2. **Layering preserved.** The data layer (`prescient.data`) stays SDK-free: the pure
   straddle-assembly method takes an INJECTED reader; the SDK-bound reader lives in
   `prescient.live_data`. `OptionQuote` is imported locally / under `TYPE_CHECKING`.
3. **Single source of truth for the as-of price.** The underlying as-of close is computed
   once (from bars the assembler already loaded) and passed into the reader for ATM
   strike selection — no redundant fetch, and the strike-selection price matches the
   EventContext's underlying price.
4. **Skip-not-guess.** Any missing piece (no contracts, only one leg, no as-of bar,
   transport error) yields an empty straddle for that event → `not_evaluable`, never a
   fabricated leg.
5. **Fetch-once cache + `--limit`.** Straddles cached per `(ticker, as_of_date)` on disk
   (existing `JsonFileCache`, normalized rows, no secrets); `--limit` bounds the first
   live run. (~2 SDK calls/event over ~200 events, so caching matters.)
6. **Propose-only.** Nothing places, sizes, authorizes, or recommends a trade.

---

## Components

### 1. `AlpacaMarketDataAdapter.get_historical_atm_straddle(...)` (pure; new method)
In `src/prescient/data/alpaca_market.py`.
- Signature: `get_historical_atm_straddle(*, underlying_symbol: str, as_of_date: date,
  underlying_price: float, earnings_date: date, max_expiration_date: date,
  feed=...) -> list[OptionQuote]`.
- Takes an injected `historical_option_reader` callable (constructor arg, like the
  existing `option_chain_reader` / `daily_bars_reader`). The reader returns normalized
  rows: `(contract_symbol, strike, expiration_date, option_type, close, open_interest)`
  for candidate contracts already fetched on `as_of_date`.
- Pure logic: filter to `earnings_date <= expiration <= max_expiration_date`; among CALLs
  pick the strike nearest `underlying_price`; pick the PUT at that SAME strike (nearest
  if exact absent); require BOTH legs to have a non-None close; build two `OptionQuote`s
  with `bid = ask = close`, `quote_date = as_of_date`, the contract strike/expiration,
  `open_interest`. Return `[call, put]`, or `[]` if either leg unavailable.
- Tie-break: equidistant strikes resolve deterministically (lower strike wins).
- No SDK import; `OptionQuote` imported locally / `TYPE_CHECKING`. Errors via the
  adapter's existing `_record` + secret-safe `_classify`.

### 2. `build_historical_option_reader(*, api_key_id, api_secret_key)` (SDK; new)
In `src/prescient/live_data/alpaca_readers.py`.
- Returns a callable
  `(underlying_symbol, as_of_date, earnings_date, max_expiration_date)
   -> list[HistoricalOptionRow]`.
- SDK dance: `get_option_contracts(status="inactive", type=call|put,
  expiration_date_gte=earnings_date, expiration_date_lte=max_expiration_date)` for both
  types; collect candidate symbols; batch `get_option_bars(symbol_or_symbols=[...],
  start/end bracketing as_of_date, timeframe=Day)`; for each contract take the bar dated
  on/just-before `as_of_date`; emit normalized rows (close from the bar). The only
  SDK-bound piece; read-only (TradingClient `paper=True` for metadata only; no execution
  adapter).

### 3. `as_of_price_for(...)` helper + option-loader rewire
In `src/prescient/edge/data/assembler.py` and
`src/prescient/edge/data/option_loader.py`.
- `as_of_price_for(ticker, report_date, bars) -> tuple[date, float] | None`: derive the
  last trading day `<= report_date - 1 day` and its close from `bars` (reuses the same
  anchor logic the assembler already applies). Single place for as-of price.
- `load_option_quotes_for_events(adapter, *, events, as_of_prices, max_expiration_days)`:
  `as_of_prices` maps `(ticker, report_date) -> (as_of_date, underlying_price)`; for each
  event with a known as-of price, call `get_historical_atm_straddle(...)`; accumulate per
  ticker; existing `try/except -> continue` skip-not-guess retained. Events with no
  as-of price are skipped (the assembler will drop them anyway).

## Data flow (live script)

```
earnings -> announcements
bars (Alpaca, batched) --> per event: as_of_date + underlying close (as_of_price_for)
                                  |
                                  v
        historical option reader (per event: list expired contracts -> ATM pair
                                   -> as_of daily bars -> [call, put] @ close)
                                  |
                                  v
announcements + bars + option_quotes -> assembler -> EventContexts (implied move computable)
                                  -> run_edge_backtest -> scorecards (option axis now real)
```

## Error handling (skip-not-guess)

- No expired contracts in window -> `[]` -> event `not_evaluable / missing_implied_move`.
- Only one leg available -> `[]` (a straddle needs both). Never fabricate the other leg.
- No bar on as_of for a leg -> that leg missing -> `[]`.
- SDK/transport error -> caught at the loader's `try/except -> continue`; counted in the
  coverage summary, not fatal.
- All drops surface in the script's coverage summary.

## Caching

Straddle per `(ticker, as_of_date)` cached on disk via the existing `JsonFileCache`
(normalized `OptionQuote` rows, no secrets). Re-runs free; first run bounded by `--limit`.

## Testing

TDD, injected fakes, no live calls in the suite:
- `get_historical_atm_straddle`: fake reader rows -> asserts nearest-strike CALL+PUT,
  `bid=ask=close`, `quote_date=as_of_date`, expiration-window filter; returns `[]` on
  missing leg / no contracts / no bar; deterministic tie-break (lower strike).
- `as_of_price_for`: nearest prior trading-day close from bars; None when no prior bar.
- `option_loader`: updated for `as_of_prices` arg; threads price through; skip-not-guess
  on reader exception; accumulates per ticker.
- `build_historical_option_reader` (SDK): NOT in the suite (needs keys); verified by
  import/parse + a live `--limit` smoke run.

## File layout

```
src/prescient/data/alpaca_market.py         # + get_historical_atm_straddle (pure)
src/prescient/live_data/alpaca_readers.py    # + build_historical_option_reader (SDK)
src/prescient/edge/data/assembler.py         # + as_of_price_for helper; expose as-of map
src/prescient/edge/data/option_loader.py     # rewire to historical straddle + as_of_prices
scripts/run_edge_backtest.py                 # wire historical reader; drop KNOWN-LIMITATION note
tests/test_edge_data_historical_options.py   # adapter method + tie-break + as_of_price_for
tests/test_edge_data_option_loader.py        # updated for new signature
```

Frozen scoring modules untouched; `get_atm_option_quotes` (current-chain) kept as a
sibling.

## Success criteria

- `get_historical_atm_straddle` returns a real ATM straddle from fake-reader data and
  `[]` on every missing-data path; tie-break deterministic. All unit tests green.
- `option_loader` + `as_of_price_for` thread the as-of price through with no redundant
  fetch; existing suite stays green.
- `scripts/run_edge_backtest.py --limit 20` against live keys produces a scorecard where
  the option columns (implied move, beat-implied, option P&L) are POPULATED for a real
  number of evaluable events (not all `not_evaluable`), with an honest coverage +
  sample-size label. The KNOWN-LIMITATION note is removed once this holds.

## Explicitly deferred (later sub-projects)

- News / sentiment / analyst-revision collectors.
- The blending prediction engine and selectivity gate.
- Dashboard.
- Forward paper-trading (only if the backtest survives).
