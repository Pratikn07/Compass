# Cron Operations

R10 standardizes scheduled jobs as cron-compatible, bounded commands. Cron is a
trigger only: it must not introduce continuous polling, broker execution side
effects, or execution-mode changes.

## Default Mode

Scheduled jobs are propose_only by default. A scheduled command may prepare or
record work for review, but it must not bypass deterministic risk gates, broker
source-of-truth checks, kill switches, daily halts, or preflight checks.

## Local SQLite State

Use SQLite for local scheduler run state:

```bash
mkdir -p var
```

The default local database path for examples is:

```text
var/prescient.sqlite
```

## Sample Cron Guard Entry

This sample records a bounded cron guard run and exits. It does not fetch live
data or execute trades.

```cron
30 6 * * 1-5 cd /path/to/prescient && uv run prescient scheduler cron-guard --job-name scheduled-strategy --run-key "$(date +\%F)" --scheduled-for "$(date +\%F)" --database-path var/prescient.sqlite --command-label propose-only-scheduled-strategy
```

## Phase D Live-Data Cron

Phase D replaces the seeded scheduled job with one bounded provider-data run:

```bash
uv run prescient live-data-run --current-date "$(date +%F)" --universe-path config/themes.yaml --storage-write-policy required
```

The command loads `config/themes.yaml`, constructs configured read-only provider
adapters, calls the Phase B/C input assembler, runs the existing scheduled
strategy pipeline, writes Supabase run/provider/decision audit rows, and exits.
It remains Claude-free, broker-free, and `propose_only`.

Required Railway environment:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `PRESCIENT_STORAGE_SCHEMA=prescient_storage`
- `FINNHUB_API_KEY`
- `FMP_API_KEY`
- the Phase C options-provider credentials required by the assembler

Optional enrichments:

- `ALPHAVANTAGE_API_KEY`
- `SEC_EDGAR_USER_AGENT`

Only one scheduled job should be active for a given trading date. Keep
`uv run prescient seed-run` available as a manual rollback command, but do not run
the seed cron and live-data cron concurrently.

## Phase E Provider Runtime

The live-data command routes provider adapters through `prescient.data.runtime`.
The wrapper enforces per-provider call budgets, reads and writes provider
snapshots, retries only retry-safe provider failures, writes secret-safe provider
errors, and upserts a `provider_health` `system_health` row for `/runs`.

Provider budgets can be tuned with:

- `PRESCIENT_PROVIDER_DAILY_BUDGETS_JSON`
- `PRESCIENT_PROVIDER_RUN_BUDGETS_JSON`

The browser only reads provider-health rows through authenticated Supabase
access. Service-role credentials remain backend-only.

## Required Properties

- Jobs are bounded and have no infinite polling.
- Commands use `uv run prescient ...`.
- Duplicate `(job_name, run_key)` executions are ignored once completed.
- Overlapping started jobs return successfully without invoking another run.
- SQLite stores local scheduler state.
- propose_only remains the documented default for scheduled automation.
- Live-data cron writes observable no-candidate or degraded run state instead of
  crashing when provider data is incomplete.
