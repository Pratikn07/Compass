# Cron Operations

R10 standardizes scheduled jobs as cron-compatible, bounded commands. Cron is a
trigger only: it must not introduce continuous polling, live provider fetching,
or broker execution side effects.

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

## Sample Cron Entry

This sample records a bounded cron guard run and exits. It does not fetch live
data or execute trades.

```cron
30 6 * * 1-5 cd /path/to/prescient && uv run prescient scheduler cron-guard --job-name scheduled-strategy --run-key "$(date +\%F)" --scheduled-for "$(date +\%F)" --database-path var/prescient.sqlite --command-label propose-only-scheduled-strategy
```

## Required Properties

- Jobs are bounded and have no infinite polling.
- Commands use `uv run prescient ...`.
- Duplicate `(job_name, run_key)` executions are ignored once completed.
- Overlapping started jobs return successfully without invoking another run.
- SQLite stores local scheduler state.
- propose_only remains the documented default for scheduled automation.
