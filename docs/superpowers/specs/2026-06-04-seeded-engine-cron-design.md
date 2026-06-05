# Seeded Engine Cron — Design

**Date:** 2026-06-04
**Status:** Approved-in-progress (proceeding under active goal), pending plan
**Scope:** A scheduled job (Railway cron) that runs the REAL deterministic pipeline
over a curated seed input set and writes real `runs` / `decision_records` /
`journal_records` to the hosted Supabase, so the dashboard shows real engine output
instead of empty states. Live provider-data fetching is explicitly OUT of scope
(separate future project).

---

## Why

The hosted Supabase `prescient_storage` tables are empty — the engine has never
written to them. The pipeline (`run_scheduled_strategy_pipeline`) and a
`SupabaseStorageAdapter` exist, but nothing assembles inputs and runs them on a
schedule. The full live-data path (Finnhub/FMP/AlphaVantage fetch + assemble +
keys + rate limits) is a large separate project. This seeded cron proves the whole
cron → pipeline → storage → dashboard chain today, with no provider keys, using
authentic engine output (the validated bullish NTNX / AI-storage candidate).

---

## 1. Architecture & components

```
Railway Cron (daily schedule)
   │ runs: prescient seed-run
   ▼
prescient.seed (NEW)
   ├── inputs.py: build_seed_inputs()  -> StrategyUniverse + upcoming_events
   │              + peer_results + target_market_data + options_chains (typed builders)
   └── run.py:    run_seed_pipeline()  -> run_scheduled_strategy_pipeline(
                     inputs…, enable_claude_analysis=False,
                     storage_writer=SupabaseStorageAdapter.from_env(),
                     storage_write_policy="required")
   ▼
Supabase prescient_storage  (runs, decision_records, journal_records)
   ▼
Vercel dashboard renders real decisions
```

Two new units, each one responsibility:
- **`src/prescient/seed/inputs.py`** — owns the seed data (curated universe + one
  bullish candidate mirroring the validated NTNX/AI-storage fixture). Pure, no I/O.
- **`src/prescient/seed/run.py`** — orchestrates build → construct Supabase writer
  from env → run real pipeline (required write policy) → return a summary. Exposes a
  callable usable both as a CLI (`prescient seed-run`) and as a cron job body.

The seed content mirrors the acceptance-test fixture VALUES but is its own owned
artifact (not an import of test code — keeps prod cron independent of tests).

---

## 2. Idempotency & scheduling

- **Idempotent by construction.** `SupabaseStorageAdapter` upserts on stable,
  deterministic IDs (`run_id` = `scheduled:<date>` / `runtime:<date>`;
  `journal_record_id` / `decision_id` derived deterministically). Re-running the
  same day overwrites identically rather than duplicating. No persistent local
  state required.
- **No SQLite cron-guard dependency.** The existing `cron-guard` uses a SQLite file
  for dedup, which does not persist on Railway's ephemeral disk. Given the
  deterministic-ID idempotency above, the seed cron does not need it. (If durable
  run-state is wanted later, a Railway volume or a Supabase `runs` check can be
  added — out of scope now.)
- **Schedule:** a standard Railway cron expression (e.g. daily pre-market). The job
  runs a single bounded pass and exits — never an infinite loop (matches the README
  "bounded, propose-only" rule).

---

## 3. Error handling & safety

- **`storage_write_policy="required"`** — if the Supabase write fails, the job exits
  non-zero; Railway marks the run failed (loud, not silent). The pipeline already
  raises under required policy on write error.
- **Propose-only, Claude-free, no broker adapter** — `enable_claude_analysis=False`,
  no `broker_adapter`. The cron physically cannot place/size/approve a trade; it only
  proposes and journals. Mirrors the hard rails. No `ANTHROPIC_API_KEY` needed.
- **Secrets:** reuses the SAME env already set on Railway for the operator service —
  `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. No new secrets introduced.
- **Bounded:** single pass, deterministic, then exit.

---

## 4. Testing

- **Unit — `build_seed_inputs()`**: returns a universe + candidate that the real
  engine turns into a non-rejected (`proposed` / candidate-ready) decision — asserts
  the seed yields a renderable decision, not a no-trade.
- **Integration — `run_seed_pipeline()`** with a FAKE storage writer (repo's existing
  fake-client pattern): asserts it calls `append_decision_journal_records` with
  run/decision/journal rows; asserts `required` policy raises on write failure.
- **No live Supabase in the suite** — fake writer only; CI stays DB-free.
- **Live verification (deploy step, not a unit test):** after Railway deploy, confirm
  rows land in hosted `prescient_storage` and the dashboard shows the decision.

---

## 5. Out of scope (YAGNI)

- Live provider-data fetching (Finnhub/FMP/AlphaVantage) — separate future project;
  needs API keys.
- Claude analyst / sub-agent analysis in the cron.
- Broker execution of any kind.
- Persistent SQLite cron-guard state / Railway volumes.
- Multiple seed scenarios — start with one clear bullish candidate; more can be added
  to `inputs.py` later.

---

## 6. Definition of done

- `prescient.seed` module (`inputs.py` + `run.py`) exists; `prescient seed-run` CLI
  works.
- Unit + fake-writer integration tests pass; full backend suite stays green; ruff clean.
- Deployed as a Railway scheduled job using the existing Supabase env.
- A real decision row is present in hosted `prescient_storage` and the Vercel
  dashboard renders it (decisions list + chain) instead of "No run yet today."
