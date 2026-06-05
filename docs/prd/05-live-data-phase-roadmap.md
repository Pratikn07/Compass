# Live Provider Data — Phase Roadmap

**Status:** Roadmap (phase structure approved). PRDs written per-phase, in order.
**Goal:** Replace the seeded engine cron with real daily earnings/peer/market data so
the engine produces varied, real decisions every day.

---

## Context (what already exists)

The data adapters are **already built** — real HTTP clients with injectable transports:

| Adapter | File | Lines | Produces |
|---|---|---|---|
| Finnhub earnings | `data/finnhub.py` | ~958 | earnings calendar, company earnings, EPS/revenue estimates+actuals |
| FMP stock peers | `data/fmp.py` | ~482 | peer ticker lists |
| AlphaVantage news | `data/alpha_vantage.py` | ~471 | news sentiment |
| SEC EDGAR | `data/sec_edgar.py` | ~324 | fundamentals/filings (User-Agent only, no key) |
| financial_datasets | `data/financial_datasets.py` | ~402 | (alt fundamentals) |

**The real gaps (not "build adapters"):**
1. Nothing **assembles** adapter outputs into the pipeline's typed inputs
   (`PeerResult`, `TargetMarketData`, `EarningsCalendarEvent`, indicators) — only
   Finnhub partially maps.
2. **No options-chain provider** exists — `OptionContractSnapshot` is consumed by the
   pipeline but produced by nothing.
3. No **orchestration** that fetches → assembles → runs → stores for a real universe.
4. Provider **API keys** not configured.

Supabase already has `provider_snapshots` and `provider_errors` tables (caching +
error capture scaffolding for this work).

---

## Phases

### Phase A — Provider readiness & contract audit
Obtain API keys (Finnhub, FMP, AlphaVantage; SEC = User-Agent). Verify each existing
adapter against the live API (response shapes drift over time) and produce a
contract-audit: what each returns vs. what the pipeline needs. Unblocks + de-risks
everything downstream. **(PRD: this phase first.)**

### Phase B — Input assembly layer
Build `assemble_pipeline_inputs(universe, date)` — calls the adapters and maps their
outputs into the typed pipeline inputs. The core missing piece. Fully tested with
recorded fixtures (no live calls in CI).

### Phase C — Options-chain data
Net-new: pick/build a provider for `OptionContractSnapshot` (the pipeline needs it;
nothing produces it today). Its own phase because it's new, not just wiring.

### Phase D — Live orchestration & real cron
Define the real watch universe; replace the seed cron with a live job:
assemble → pipeline → Supabase on schedule, with provider error handling (rate limits,
partial failures, missing data → graceful skip, never crash).

### Phase E — Hardening & observability
Rate-limit budgeting, caching via `provider_snapshots`, retries, cost control, and
provider health surfaced on the `/runs` dashboard. Production-trustworthy.

---

## Workflow

Per the user's choice: **PRD Phase A now**, decide subsequent phases after. Each phase
follows the repo standard: brainstorm → PRD (`docs/prd/`) → plan (`docs/superpowers/plans/`)
→ TDD build. Live-data fetching stays read-only, Claude-free, propose-only, broker-free
— same rails as the rest of the system.
