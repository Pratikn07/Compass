# PRD: R5C Full Live Inputs & Options Chain

## Ownership

- **Layer:** `prescient.data`, `prescient.live_data`, `prescient.scheduler`,
  and `prescient.storage`.
- **Phase:** C of the Live Provider Data roadmap, expanded by product decision
  into one thin end-to-end live-data vertical.
- **Depends on:** R5A provider configuration readiness, existing Finnhub/FMP/
  AlphaVantage/SEC adapters, the deterministic scheduler pipeline, Supabase
  storage tables, and the existing propose-only execution rails.

## Objective

Replace the seeded scheduled pipeline path with a bounded live-provider-data run
that assembles real typed inputs, includes a real options chain, runs the existing
deterministic strategy pipeline, and writes observable provider/run state.

R5C answers:

```text
Can Prescient run the earnings read-through pipeline from real provider inputs,
including options-chain liquidity, without invoking Claude, brokers, or live
trading?
```

This is **live data**, not live trading. The phase remains read-only with
providers, broker-free, Claude-free, and propose-only by default.

## Background

The original live-data roadmap split the work into:

- Phase B: input assembly.
- Phase C: options-chain data.
- Phase D: live orchestration and real cron.

For this PRD, the chosen product direction intentionally collapses those into a
single thin vertical. The system should no longer prove only that options data can
be fetched in isolation; it should prove that real provider data can flow through
the same typed contracts the deterministic engine already consumes.

Existing facts:

- `run_scheduled_strategy_pipeline(...)` already accepts structured
  `EarningsCalendarEvent`, `PeerResult`, `TargetMarketData`,
  `OptionContractSnapshot`, and optional `TechnicalIndicatorSnapshot` inputs.
- Existing adapters cover Finnhub, FMP, AlphaVantage, and SEC EDGAR, but no
  adapter currently produces options-chain snapshots.
- Supabase already has `provider_snapshots` and `provider_errors` tables, but the
  storage adapter must expose concrete append methods for them.
- Alpaca is already the primary broker dependency and the installed `alpaca-py`
  SDK also exposes read-only market-data clients.

Alpaca is the selected primary provider for options-chain and stock-bar market
data because it minimizes new dependency and credential surface. Current Alpaca
documentation exposes an option-chain snapshots endpoint by underlying symbol,
an option contracts endpoint with metadata/open interest, and `alpaca-py`
`OptionHistoricalDataClient.get_option_chain(...)` / contract APIs.

## Functional Requirements

### R5C.1 Provider Configuration

Extend the provider configuration seam so live-data runs can construct all
required read-only provider clients from environment configuration.

Required env vars:

```text
FINNHUB_API_KEY
FMP_API_KEY
ALPACA_API_KEY_ID
ALPACA_API_SECRET_KEY
```

Optional env vars:

```text
ALPHAVANTAGE_API_KEY
SEC_EDGAR_USER_AGENT
ALPACA_OPTIONS_FEED=indicative | opra
```

Rules:

- `ALPACA_OPTIONS_FEED` defaults to `indicative`.
- `indicative` must be documented as delayed/derived option data.
- `opra` may be configured only when the account has the required subscription.
- Missing required providers fail configuration before any provider call.
- Missing optional providers degrade enrichment only.
- No key, secret, authorization header, raw provider payload, or service-role
  value may appear in repr, logs, CLI output, storage errors, or test fixtures.

### R5C.2 Alpaca Market-Data Adapter

Add a read-only Alpaca market-data adapter under `prescient.data`.

The adapter must not import or construct broker execution adapters. It may use
Alpaca SDK market-data and trading-contract metadata clients only for reads.

Required capabilities:

```python
get_option_chain_snapshots(
    *,
    underlying_symbol: str,
    earnings_date: date,
    max_expiration_date: date,
    feed: Literal["indicative", "opra"] = "indicative",
    fetched_at: datetime | None = None,
) -> list[OptionContractSnapshot]

get_daily_bars(
    *,
    symbols: Sequence[str],
    start: date,
    end: date,
) -> dict[str, list[DailyBarSnapshot]]
```

Options-chain mapping:

- Fetch active call option contracts for the target ticker.
- Restrict expirations to `earnings_date <= expiration <= max_expiration_date`.
- Merge contract metadata (`symbol`, `strike_price`, `expiration_date`,
  `open_interest`) with latest option-chain quote snapshots (`bid`, `ask`).
- Emit existing `OptionContractSnapshot` records.
- Keep existing required fields stable: `ticker`, `option_type`,
  `expiration_date`, `bid`, `ask`, `open_interest`, `source_citations`.
- Add only optional metadata fields, such as `contract_symbol`,
  `strike_price`, `quote_timestamp`, and `source_feed`.
- Do not expose `strike`, IV, greeks, side, credit, breakeven, or multi-leg
  proposal fields in `data_snapshot.options_chain_summary` in this phase.

Determinism:

- Normalize ticker symbols uppercase.
- Sort option snapshots by `expiration_date`, then `strike_price`, then
  `contract_symbol`.
- Treat missing quote or missing open interest as a usable audit snapshot but not
  a liquid option; the existing strategy liquidity rules must fail or fall back
  deterministically.
- Convert Alpaca auth, 403 subscription, 429 rate limit, malformed response, and
  unsupported symbol failures into `DataProviderError` values.

### R5C.3 Live Input Assembly

Add a live input assembly seam, for example:

```python
assemble_live_pipeline_inputs(
    *,
    run_id: str,
    universe: StrategyUniverse,
    current_date: date,
    provider_config: ProviderConfig,
    provider_adapters: Mapping[str, object],
    settings: StrategySettings,
) -> AssembledLivePipelineInputs
```

The assembly result must include:

```python
class AssembledLivePipelineInputs(BaseModel):
    universe: StrategyUniverse
    upcoming_events: list[EarningsCalendarEvent]
    peer_results: list[PeerResult]
    target_market_data: dict[str, TargetMarketData]
    options_chains: dict[str, list[OptionContractSnapshot]]
    indicator_snapshots: dict[str, TechnicalIndicatorSnapshot] | None = None
    provider_snapshots: list[dict[str, Any]]
    provider_errors: list[DataProviderError]
    skipped_targets: list[str]
```

Assembly behavior:

- Load the strategy universe from `config/themes.yaml`; providers must not add,
  remove, or rewrite configured themes.
- Use Finnhub earnings calendar for upcoming target events inside the configured
  earnings window.
- Use Finnhub earnings actuals/estimates for same-theme peers that reported
  inside `peer_result_window_days`.
- Use Alpaca daily stock bars to compute peer `price_reaction_pct`.
- Keep `guidance_signal` and `theme_driver_signal` as `"unknown"` unless a later
  phase adds deterministic derivation.
- Use Alpaca daily bars to compute `TargetMarketData.avg_daily_volume` from the
  trailing 30 trading sessions.
- Use Alpaca daily bars to compute `TargetMarketData.pre_earnings_runup_pct`
  from the trailing 5 trading sessions.
- Use Alpaca option-chain snapshots for every target with an upcoming earnings
  event.
- Emit best-effort indicator snapshots only when all required indicator fields
  can be computed from available bars; otherwise omit the snapshot or list
  missing fields explicitly.

Missing data policy:

- Missing or partial provider data must not crash the cron job.
- Provider failures must be captured in `provider_errors`.
- Targets that cannot be assembled must be listed in `skipped_targets`.
- A no-candidate run must still write observable run/provider status.
- The deterministic strategy engine remains responsible for final rejections,
  including `MISSING_DATA` and `OPTIONS_TOO_ILLIQUID`.

### R5C.4 Live Run Command

Add a bounded CLI command:

```bash
uv run prescient live-run \
  --current-date 2026-06-01 \
  --universe-path config/themes.yaml \
  --storage-write-policy required
```

If a local implementation already exposes `live-data-run`, keep it as a
compatibility alias or migrate it to `live-run` with tests covering the public
command. The product-facing command for this PRD is `live-run`.

Command behavior:

- Load provider config from environment.
- Load the universe YAML.
- Assemble live inputs.
- Run `run_scheduled_strategy_pipeline(...)`.
- Set `enable_claude_analysis=False`.
- Do not construct broker adapters.
- Do not place, size, approve, or authorize trades.
- Write Supabase storage when configured.
- Print a secret-safe summary: run id, decision count, provider error count,
  skipped target count, and whether storage was written.
- Exit non-zero only for configuration errors or required storage write failures.

### R5C.5 Storage Writes

Implement concrete storage methods for provider audit state:

```python
append_provider_snapshots(snapshots: Iterable[dict[str, Any]]) -> StorageWriteResult
append_provider_errors(errors: Iterable[dict[str, Any]]) -> StorageWriteResult
upsert_run_status(record: RunStatusRecord) -> StorageWriteResult
```

Provider snapshot rows must be bounded and queryable:

- `provider_snapshot_id`: deterministic id including run/provider/source/target.
- `provider`: lower-case provider name, including `alpaca`.
- `target`: ticker when applicable.
- `theme`: configured strategy theme when applicable.
- `source_endpoint`: provider endpoint or adapter method.
- `source_id`: provider symbol or logical source key.
- `as_of`: market/data date.
- `retrieved_at`: UTC timestamp.
- `payload`: redacted representative payload, not unbounded raw provider output.

Provider error rows must include:

- `provider_error_id`.
- `provider`.
- `error_type`.
- `run_id`.
- `target` when applicable.
- `source`.
- secret-safe `message`.
- bounded `payload` with status code and retry-after when available.

When no strategy decisions are produced, the run must still upsert a `runs` row
with status such as `no_candidates` or `degraded` so the dashboard does not look
empty or stale.

### R5C.6 Cron Replacement

Keep `seed-run` available for manual rollback and deterministic fixtures.

Update operational docs so the scheduled production path is the bounded live run:

```cron
30 6 * * 1-5 cd /path/to/prescient && uv run prescient live-run --current-date "$(date +\%F)" --universe-path config/themes.yaml --storage-write-policy required
```

Only one scheduled job should be active for a trading date. The seed cron and
live-data cron must not run concurrently.

## Acceptance Criteria

1. `ProviderConfig` supports Alpaca market-data credentials and an options feed
   value defaulting to `indicative`, with secret-safe repr/log behavior.
2. `DataProvider` includes `alpaca`.
3. The Alpaca market-data adapter is unit-tested with injected fake clients and
   makes no live calls in pytest.
4. Option-chain adapter tests cover pagination, snapshot batching, missing bid,
   missing ask, missing open interest, auth failure, subscription/permission
   failure, rate limiting, unsupported symbol, and feed selection.
5. `OptionContractSnapshot` keeps all existing required fields stable; any new
   fields are optional and do not break existing fixtures.
6. `options_chain_summary` continues exposing only ticker, option type,
   expiration, bid, ask, and open interest.
7. Live assembly tests prove fake Finnhub and Alpaca payloads produce typed
   upcoming events, peer results, target market data, option chains, provider
   snapshots, and provider errors.
8. Missing provider data records errors and skipped targets, degrades observable
   run state, and does not crash the live run.
9. `prescient live-run` is bounded, secret-safe, defaults to propose-only, sets
   `enable_claude_analysis=False`, imports no broker adapter, and creates no
   broker order.
10. Supabase storage tests cover `append_provider_snapshots`,
    `append_provider_errors`, and `upsert_run_status`.
11. Existing seeded pipeline tests and frontend real-payload contract tests
    remain green.
12. `uv run pytest -q` and `uv run ruff check .` pass.

## Non-Goals

- Live trading or any real-money execution.
- Paper trading execution.
- Broker adapter construction.
- Claude analyst invocation.
- Multi-leg option strategies or structured option-leg proposals.
- Changing risk caps or target filter thresholds.
- Buying or provisioning Alpaca OPRA subscriptions.
- Replacing the dashboard UI beyond existing runs/provider/system-health data
  becoming populated.
- Streaming market data or continuous polling.
- Perfect guidance/theme-driver extraction from transcripts.

## Risks & Mitigations

### Indicative option data quality

Alpaca's free indicative option feed is delayed/derived. The run must record the
feed in option citations/snapshots and allow `ALPACA_OPTIONS_FEED=opra` only when
the account is entitled.

### Provider rate limits

The assembly layer must bound per-run calls by universe size, fetch only the
configured themes, and record rate-limit errors as provider errors. Retrying and
cost budgeting beyond basic safe failure remain Phase E hardening work.

### Empty live days

Some days will have no configured target earnings or insufficient peer context.
The command must write a no-candidate/degraded run record rather than depending
on decision rows alone.

### Contract drift

Live provider response shapes can drift. All adapters must parse into internal
Pydantic/data models at the edge and keep raw payloads out of hot-path strategy
code.

## Product FAQ

**Q: Why does Phase C include assembly and cron replacement?** Product direction
changed the phase from a standalone options provider into a thin full live-input
vertical. This prevents a working options adapter from remaining disconnected
from the actual scheduled strategy pipeline.

**Q: Does this authorize live trading?** No. This phase only fetches live market
data. It remains propose-only, broker-free, Claude-free, and inside the existing
code-owned rails.

**Q: Why Alpaca for options?** Alpaca is already in the tech stack, supports
option contract metadata and option-chain snapshots, and avoids adding a new
vendor before the first live-data vertical is proven.

**Q: Why keep `seed-run`?** The seeded run remains useful as a deterministic
fixture and rollback path. It should not be the production scheduled data path
once the live run is configured.
