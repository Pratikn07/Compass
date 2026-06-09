# Vanta — Step 1: Data Warehouse Foundation (Design Spec)

**Date:** 2026-06-08
**Status:** Approved for planning
**Author:** Pratik (with Claude)

---

## 1. Context & Goal

Vanta is a fresh-start app to assess whether an options trade around a company's
earnings is likely to be profitable. The deliberate first target is **Micron (MU)**,
which reports **fiscal Q3 2026 on Wednesday, June 24, 2026, after market close**
(confirmed via Micron's announcement, Wall Street Horizon, and Stock Analysis).

**This spec covers Step 1 only: the data warehouse foundation.** No predictions, no
options data, no UI. The goal is to stand up a Supabase Postgres warehouse and prove we
can fill it — for **zero spend** — with enough free-layer intelligence on MU and its
competitive space to later test a read-through thesis, built with point-in-time
correctness so we never inherit the look-ahead bias that sinks most retail projects.

### Why this sequencing
One step at a time, invest only once proven. Step 1 spends nothing and validates the
pipeline + data quality. Only after we *see* the data do we buy the paid
implied-volatility / options layer (Step 2) that the research shows is the make-or-break
ingredient.

---

## 2. The Core Reframing (from research)

The naive hypothesis — "buy options ~7 days before earnings → profit" — is the exact
strategy that most commonly **fails**, because of **IV crush**: implied volatility
inflates option premiums before earnings, then collapses 30–60% the moment results drop,
so options can lose 30–70% of value *even when direction is correct*.

**Therefore the app's real question is not "will the stock go up?" but
"will the stock move MORE than the options market already expects (the implied/expected
move)?"** This reframing drives all later modeling. Step 1 builds the foundation that a
later expected-move model will sit on.

### Why other GitHub/Reddit projects fail (and our countermeasures)
| Failure mode | Countermeasure (designed in from Step 1) |
|---|---|
| Overfitting (noise, not signal) | Keep models simple; out-of-sample testing (later steps) |
| Look-ahead bias / data leakage | **Point-in-time storage** — every row carries `ingested_at`; never overwrite history |
| Survivorship bias | Train on a wide universe, not just today's winners (later steps) |
| Ignoring IV crush | Model expected-move, not direction; requires paid IV layer (Step 2) |
| Ignoring costs/slippage | Include bid-ask + IV crush in any P&L estimate (later steps) |
| Tiny sample size | Trade MU, but *learn* from many tickers' earnings history (later steps) |

The single most important safeguard built in **now** is point-in-time correctness — cheap
to build now, expensive to retrofit.

---

## 3. Scope

**Tickers (Step 1 universe — "AI Memory" theme):**
MU (target) + WDC, SNDK (direct memory/NAND rivals) + NVDA, AMD, AVGO (AI demand drivers
whose GPU/accelerator demand drives MU's HBM/DRAM demand).
Foreign peers (SK Hynix, Samsung) are captured **only if** the free APIs return usable
data; coverage gaps are logged honestly, not hidden.

**In scope (Step 1):** Supabase warehouse schema + free-layer ingestion adapters +
orchestration + coverage report + tests.

**Out of scope (named, deferred):**
- Step 2: paid implied-volatility + historical options layer (ORATS ~$99+/mo or
  Polygon ~$199/mo) — the make-or-break ingredient.
- Step 3+: expected-move modeling; ML (leverage pre-built finance models e.g. FinBERT /
  HuggingFace, or train on the accumulated warehouse).
- Backtester, prediction/scoring engine, frontend.

---

## 4. Data Requirements (full picture)

| # | Data | Why needed | Source | Step 1 status |
|---|------|-----------|--------|---------------|
| 1 | Earnings dates (history + upcoming) | anchor every event | Finnhub/FMP | ✅ free |
| 2 | Stock prices (daily OHLCV) | compute realized moves | FMP/AlphaVantage | ✅ free |
| 3 | News + sentiment | the "space"/spillover signal | AlphaVantage/Finnhub | ✅ free |
| 4 | Peers / competitor graph | read-through thesis | FMP | ✅ free |
| 5 | SEC filings (8-K) | official deals/material events | EDGAR | ✅ free |
| 6 | Analyst estimates + surprise history | did it beat? by how much? | Finnhub/FMP | ✅ free |
| 7 | Earnings-call transcripts | guidance/demand language | FMP | ✅ free |
| 8 | **Historical implied volatility** | **the expected move** | ORATS/Polygon | ❌ Step 2 (paid) |
| 9 | **Historical options prices** (strike/expiry) | real option P&L | ORATS/Polygon | ❌ Step 2 (paid) |
| 10 | Options Greeks (vega/theta/delta) | quantify crush & decay | ORATS/Polygon | ❌ Step 2 (paid) |
| 11 | Historical realized earnings moves | baseline move size | derived from #2 | ✅ computable |

Step 1 delivers items 1–7 and makes 11 computable. Items 8–10 are the deliberate Step 2
investment.

---

## 5. Architecture

Small, isolated, independently testable units.

```
vanta/
  config.py                # ticker universe, theme map, peer edges, key loading
  db.py                    # Supabase client + SQL migrations
  adapters/
    finnhub.py             # news, earnings dates, estimates
    alphavantage.py        # news + sentiment
    fmp.py                 # peers, prices, press releases, transcripts
    sec.py                 # SEC EDGAR 8-K filings
  run.py                   # orchestrate adapters, log ingest_runs, print coverage report
  tests/                   # adapter tests against mocked API fixtures
  .env                     # keys (copied from prescient), gitignored
```

**Adapter contract:** each adapter exposes a uniform `fetch(ticker) -> list[record]`
returning normalized records; `run.py` writes them to the warehouse. Adapters are
swappable — adding the paid ORATS/Polygon source in Step 2 is just a new file, no change
to the orchestrator.

**Error handling:** per-source try/except — one dead API logs a gap to `ingest_runs` and
the run continues. Free-tier rate limits are throttled; responses cached during a run.

---

## 6. Warehouse Schema (Supabase Postgres)

Every fact-bearing table carries `ingested_at` (when *we* learned it), distinct from the
event's own timestamp — this is the point-in-time safeguard.

| Table | Key columns | Notes |
|-------|-------------|-------|
| `tickers` | symbol, name, theme_tags[], peer_symbols[] | the universe + competitor graph |
| `news` | ticker, source, published_at, ingested_at, headline, url, sentiment, raw(jsonb) | `ingested_at` ≠ `published_at` |
| `filings` | ticker, type, filed_at, ingested_at, url, raw(jsonb) | SEC 8-K events |
| `earnings_dates` | ticker, report_date, confirmed(bool), ingested_at | store estimate vintage |
| `estimates` | ticker, period, eps_est, rev_est, eps_actual, surprise_pct, as_of, ingested_at | as-known-at-date |
| `prices` | ticker, date, open, high, low, close, volume | for realized-move calc |
| `ingest_runs` | run_id, started_at, source, ticker, records, status, error | full provenance/audit |

Migrations live in `db.py` (or a `migrations/` SQL file) and are idempotent.

---

## 7. Stack & Prerequisites

- **Language:** Python (matches existing API keys + the ML ecosystem targeted later).
- **Libraries:** `requests`, `supabase` (Python client), `python-dotenv`, `pytest`.
- **Keys (reused from prescient, copied into gitignored `.env`):** `FINNHUB_API_KEY`,
  `FMP_API_KEY`, `ALPHAVANTAGE_API_KEY`. SEC EDGAR needs no key (requires a descriptive
  User-Agent header).
- **Supabase:** a **new, dedicated Supabase project** (clean isolation from prescient).
  **Prerequisite from Pratik:** Project URL + service-role key (+ Postgres connection
  string if available).
  **Fallback:** if the Supabase project isn't ready, build against a local Postgres so
  development isn't blocked; switch the connection string when credentials arrive.

---

## 8. Output / Definition of Done (Step 1)

- New Supabase project provisioned with the schema above (or local-Postgres fallback).
- `python run.py` ingests all 6 tickers across all 4 free sources without crashing;
  per-source failures are logged, not fatal.
- A printed **coverage report**: per-ticker counts (news / filings / estimates / prices),
  average sentiment, and explicit ⚠️ gap flags (e.g. foreign-peer coverage).
- Real, queryable rows in the warehouse, each with correct `ingested_at` provenance.
- Adapter tests pass against mocked fixtures.

**Decision gate:** after reviewing the coverage report and querying the data, decide
whether the free intelligence is rich enough to proceed to Step 2 (buy IV/options layer).

---

## 9. Open Items

- Pratik to create the new Supabase project and provide URL + service-role key.
- Confirm SEC EDGAR User-Agent string (email/identifier) for compliant access.
