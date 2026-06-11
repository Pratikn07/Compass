# Phase 3 — Backend App Design (DRAFT, conditional)

**Status: DRAFT — DO NOT IMPLEMENT.**
The rulebook gate (§7) requires ≥1 hypothesis `survived = true` across
development + sensitivity + validation before Phase 3 code exists. As of
2026-06-11 that gate is NOT passed (H1 partial/XLF-only with validation
unspent; H2/H3 awaiting fundamentals). This document exists so the build can
start the evening the gate passes — it commits to nothing the verdicts haven't
earned.

## 1. What Phase 3 is

The app's brain: a nightly batch job that updates data and recomputes the
state of every theme, persisted verdicts, and a FastAPI service (versioned
`/v1`) that serves exactly what the nightly job wrote. No front end (Phase 4),
no streaming, no broker access, propose-only forever.

```
nightly job ──> Supabase (state + recommendations + journal)
                     │
                FastAPI /v1  (read-mostly; writes: overrides, acks)
```

## 2. Scenario switch (filled in when verdicts land)

The recommendation layer is assembled ONLY from surviving hypotheses:

| Scenario | What survived | What the app recommends |
|---|---|---|
| A | H1 narrow (e.g. XLF-only) | Trend on/off state for the surviving instrument(s) only; everything else is informational |
| B | H2 and/or H3 | Quarterly theme-reality rankings and/or laggard candidates, with base rates from the harness |
| C | Nothing survives validation | Phase 3 is not built. Program-review write-up instead |

Theme trend states for ALL themes are always *displayed* (information), but
the word "consider" appears only next to signals that survived the gate.

## 3. Nightly job (`compass.nightly`)

Order, idempotent, resumable, cron-compatible (no infinite loops):

1. **Prices append** — Yahoo daily bars for the 85-ticker universe (delta
   fetch: from last stored bar; full refetch weekly to pick up adjustment
   restatements). Upsert via the existing `store.py`.
2. **Fundamentals refresh** — Alpha Vantage for members whose next report is
   due (earnings-calendar aware later; weekly round-robin within the 25/day
   cap to start).
3. **Recompute states** — importing the SAME modules the harness validated
   (`compass.backtest.series`, `h1_trend`, `h2_reality`, `h3_laggard`) — no
   reimplementation, so harness-vs-app drift is structurally impossible:
   - per theme: index level, SMA(200), trend on/off, days in state
   - per surviving hypothesis: today's candidate signals with full reasoning
     inputs (the numbers that fired the rule)
4. **Write the day** — `compass_theme_state_daily`, `compass_recommendations`
   (empty most days — "nothing to do" is a row too), `compass_ingest_runs`.
5. **Self-check** — coverage deltas; any silent-failure condition writes an
   `alerts` row the API surfaces.

## 4. New tables (one migration)

- `compass_theme_state_daily` — d, theme_slug, index_level, sma200, trend_on,
  days_in_state, ingested_at; unique (d, theme_slug)
- `compass_recommendations` — d, hypothesis, instrument, action
  (`consider_enter` | `consider_exit` | `none`), reasoning (jsonb: the exact
  inputs), base_rate (from harness results), acknowledged_at (owner saw it),
  acted_at + action_note (owner's own report); unique (d, hypothesis, instrument)
- `compass_overrides` — when the owner acts AGAINST a recommendation (or acts
  with no recommendation): timestamp, what, one-line reason (required), priced
  later by the journal
- `compass_rule_changes` — proposed change, proposed_at, effective_at
  (>= proposed_at + 48h, enforced in code), approved_by_owner

## 5. API (`/v1`, FastAPI)

Read endpoints serve ONLY persisted nightly output (no on-the-fly compute —
what you see is what was computed once, auditable):

- `GET /v1/health` — last nightly run status, data freshness, alerts
- `GET /v1/themes` — all themes with current state
- `GET /v1/themes/{slug}` — state history, members, index series (for Phase 4 charts)
- `GET /v1/recommendations/today` — the daily answer (usually: nothing to do)
- `GET /v1/journal` — recommendations vs acknowledgments vs actions; override costs
- `POST /v1/overrides` — record an owner override (reason required)
- `POST /v1/recommendations/{id}/ack` — owner saw it
- `POST /v1/rule-changes` — starts the 48-hour cooling-off clock; nothing
  applies before it elapses

No order placement endpoints exist. No broker SDK is ever a dependency.

## 6. Tests and the parity gate

- API serves byte-identical numbers to the harness on identical inputs
  (parity test: run harness state calc vs nightly job output on a pinned day)
- Nightly job is idempotent: running twice for the same date changes nothing
- Cooling-off: a rule change cannot take effect early (clock tested)
- Gate to close Phase 3 (rulebook §7): one month of nightly runs without
  silent failure + parity holding

## 7. Estimate and order of work

~2 weeks of evenings once green-lit: migration -> nightly job (reusing
backtest modules) -> parity test -> API endpoints -> journal/override flow ->
a week of supervised nightly runs before trusting it.

## 8. Out of scope

Front end (Phase 4), theme auto-detection (Phase 5), new data sources, any
signal that did not survive the gate, auto-trading (never).
