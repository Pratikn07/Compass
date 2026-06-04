# Prescient Web Frontend — Visual Target & Gap Analysis

**Date:** 2026-06-03
**Status:** Reference document — the approved *visual target* for the frontend, plus an honest map of what the running code does vs. doesn't render yet.
**Companion docs:**
- Design spec: `2026-06-03-prescient-web-frontend-design.md`
- Slice 0 plan: `../plans/2026-06-03-prescient-frontend-slice-0-shell.md`

---

## Purpose

A set of hi-fi design mockups was produced for Prescient's operator console. They
match (and exceed) the intended design language: a calm, dense, trustworthy
trading-decision-review console. **These mockups are the destination, not the
current state.** This file records:

1. What the mockups establish as the visual target (so intent isn't lost).
2. A per-element gap analysis: **exists / needs frontend work / needs backend data first.**

Use this as the backlog source when picking up frontend work. Each "needs
frontend work" cluster is large enough to deserve its own brainstorm → plan →
build slice; several items are **blocked on backend fields that do not exist yet.**

> The mockups are visual concepts (huashu/v0-style), NOT screenshots of the
> running Next.js app. Where they disagree with the code, the code is the
> current reality and the mockup is the target.

---

## The visual target (what the mockups establish)

Shared design language across all screens — keep these as invariants:

- Calm, data-dense, instrument-grade (not consumer fintech). No marketing flourish.
- Reserved semantic color: green = passed/proposed/healthy, red =
  rejected/blocked/error, amber = needs-attention/warning, grey = inert/no-action.
- Tabular numerals everywhere; monospace for tickers / run-ids / timestamps.
- Persistent top nav (Decisions · Runs · Backtest) with active indicator.
- Every data view handles loading / error / empty explicitly; errors are LOUD
  with a raw-detail drawer (never absorb backend inconsistency).
- Footer disclaimer present: "Confidence reflects model certainty, not trade outcome."
- Hard safety framing visible: no buy/sell/approve/size controls; "Advisory
  only — not authorization"; "Read-only — quantity was code-decided"; the
  mode-authorization panel fenced as a privileged action; "live" never offered in UI.

---

## Mockup inventory

Five mockups were reviewed (described here so the reference survives without the
image files):

1. **Runs / System Status** — top nav with "Engine Healthy" pill + notification
   bell + help + "AK" user menu. Four status summary cards (Execution mode /
   Scheduler last-run / Daily halt / Kill switch). "Recent runs" table (Run ID,
   Trigger, Start time, Status, Decisions count). "Provider errors (last 24h)"
   table. "Storage write audit (last 24h)" table with error-rate %. Bottom:
   fenced amber **"Mode authorization (privileged)"** panel with reason textarea,
   request-status box, "Request paper mode" / "Return to propose-only" buttons,
   and "Only authorized operators may submit."

2. **Decision Chain (detail)** — `NVDA` header with Theme / Strategy / Trading
   Date + Status (Proposed) / Outcome (Pending). Numbered vertical timeline,
   6 steps: (1) Strategy decision with "why it triggered / peer read-through
   evidence / thesis" columns; (2) Analyst review (Claude) with amber "Advisory
   only — not authorization" callout, recommendation + conviction bar + key
   considerations; (3) **Risk decision — dominant red anchor card** with big ✕
   REJECT, explanation, "Broker execution allowed: No", rejection reasons;
   (4) Position sizing with "Read-only — quantity was code-decided" callout +
   account/risk-budget/max-loss/size/confidence-adjustment; (5) Execution proposal
   with "Propose-only — no order will be sent" + structure/DTE/credit/max-loss/
   breakevens + full option-leg table; (6) Outcome. Each step has a "Source
   citations" panel (provider, doc, timestamp, link). Bottom: loud malformed
   step-payload error with raw JSON.

3. **Decisions list (simple)** — page header "Decisions" + "Latest run: <id> ·
   <date>" + run/date switcher (prev/next + dropdown). Table: Target / Theme /
   Strategy / Status / Outcome / Mode with semantic badges. Includes a malformed
   **BADROW** with ⚠ icon + "Malformed" badge + info tooltip ("Unexpected or
   invalid data in run payload" + "Show raw detail"). Shows loading skeleton,
   error panel, and "No run yet today" empty state.

4. **Decisions list (rich / sidebar)** — left sidebar: Universe (earnings
   window), Quick Filters (All / Proposed / Needs Attention / Rejected / No
   Action with counts), Watchlists, Recent Runs, System Status (Market Data /
   Pricing Engine / Risk Engine health, Data Latency). Main: KPI strip (Total
   Decisions / Proposed / Needs Attention / Rejected-Blocked / No Action / Median
   Edge BP). Search box + Status/Strategy/Min-Edge/More filter dropdowns +
   "Columns". Richer table: Ticker / Company / Earnings Date / Strategy /
   **Edge (BP)** / **Confidence** (bar) / Key Drivers / Status + row menu.
   Pagination + "5 / page". Demonstrates loading / error (with raw detail) /
   empty side by side.

5. **Backtest / Performance** — date-range + theme + more filters. KPI strip
   (Win rate / Total return / Max drawdown / Sharpe / Number of trades, each vs
   benchmark, with sparklines). Equity curve (Strategy vs Matched Buy-and-Hold)
   with hover tooltip; Drawdown area chart sharing x-axis. %/$ toggle. Results
   table (Target / Theme / Strategy / Entry / Exit / Holding days / Realized P&L %
   / Outcome) sortable + paginated + export. Loading / error / empty shown.

---

## Gap analysis

Legend: ✅ exists in code · 🟡 needs frontend work · 🔴 blocked on backend data first

### App chrome / navigation
| Element | State | Notes |
|---|---|---|
| Top nav: wordmark + Decisions/Runs/Backtest + active indicator | ✅ | `components/nav.tsx`; layout is top-nav + centered `max-w-7xl` main |
| Tagline "Propose-Only Earnings Options Engine" next to wordmark | 🟡 | trivial add |
| "Engine Healthy" status pill | 🔴 | needs an engine-health signal/source |
| Notification bell, help icon | 🟡 | UI shell; bell needs a notifications source to be meaningful |
| User menu / avatar ("AK") | 🟡 | wire to Supabase auth user; sign-out |
| Footer (timezone, data-as-of, disclaimer, doc links, version) | 🟡 | static-ish; "data as of" needs a timestamp source |

### Decisions — list
| Element | State | Notes |
|---|---|---|
| Table: Target/Theme/Strategy/Status/Outcome/Mode + semantic badges | ✅ | `features/decisions/decision-list.tsx` |
| Page header + "Latest run: <id>" | ✅ | `decision-list-client.tsx` |
| Loading / error / empty states | ✅ | wired |
| Run/date switcher (prev/next + dropdown) | 🟡 | currently shows latest run statically; needs run-history query + selector |
| Malformed-row loud surfacing (⚠ badge + tooltip + raw detail) | 🟡 | **known finding**: `parse-decision-list.ts` currently silently falls back to `{}`; must surface loudly like the chain does |
| Decision count chip | ✅ | added during polish |
| Left sidebar (Universe / Quick Filters / Watchlists / Recent Runs / System Status) | 🟡/🔴 | net-new layout; filters need query params; System-status health + watchlists need backend sources |
| KPI strip (Total/Proposed/Needs Attention/Rejected/No Action/Median Edge) | 🔴 | needs aggregate counts + an "edge (bp)" metric that the schema does not currently expose |
| Search box | 🟡 | client filter is doable; server search needs an endpoint for large sets |
| Filter dropdowns (Status/Strategy/Min Edge/More) | 🟡/🔴 | status/strategy are filterable from existing fields; min-edge needs the edge metric |
| Pagination + per-page | 🟡 | needs paged query (Supabase range) |
| Columns: Company name, Earnings Date, Edge (BP), Confidence bar, Key Drivers | 🔴 | **none of these exist as columns today**; company name / earnings date / edge / confidence / key-drivers must be confirmed/added in backend payloads first |
| "Needs Attention" status value | 🔴 | not a current status enum value; backend decision |

### Decisions — chain (detail)
| Element | State | Notes |
|---|---|---|
| Numbered vertical timeline, 6 ordered steps | ✅ | `decision-chain-view.tsx` |
| Risk card as dominant red anchor + PASS/REJECT + reasons | ✅ | incl. "Broker execution allowed: Yes/No" |
| "Advisory only — not authorization" callout | ✅ | analyst step |
| "Read-only — quantity was code-decided" callout | ✅ | position-sizing step |
| Malformed step-payload loud error + raw JSON | ✅ | parse boundary done right here |
| Source citations panel per step | ✅ | `source-citations.tsx` |
| Header: target + theme + status/outcome badges | ✅ (partial) | renders target/theme/ids; status/outcome badges in header are lighter than mockup |
| Strategy step: peer read-through evidence as distinct columns | 🟡 | currently thesis + metadata grid; mockup shows richer 3-column evidence layout (depends on payload fields present) |
| Execution proposal: full option-leg table (side/qty/type/expiry/strike/IV/price/credit) | 🔴 | currently a raw-JSON `<details>` dump; a real leg table needs those structured fields in the execution payload |
| Position sizing: "confidence adjustment", "account/book" fields | 🔴 | mockup shows fields (e.g. Alpha Book, confidence 0.92) not confirmed in current payload |

### Runs / System status
| Element | State | Notes |
|---|---|---|
| Four summary cards (mode / scheduler / daily halt / kill switch) | ✅ | `runs-summary-cards.tsx` |
| Recent runs table | ✅ | |
| Provider errors table | ✅ | |
| Storage write audit table (+ error rate %) | ✅ | error-rate % column may need adding |
| Fenced "Mode authorization (privileged)" panel | ✅ | polished into a cordoned accent zone; reason field + paper/propose-only buttons; live never offered |
| Reason as multiline textarea + char counter (0/1000, min 10) | 🟡 | currently a single-line `Input` with no counter; mockup shows textarea + counter |
| Request-status box ("No request submitted…") | 🟡 | currently inline result text; mockup shows a dedicated status panel |
| "live" not rejected at the API route handler | 🟡 | **known finding** (defense-in-depth): route schema accepts "live"; UI/client don't send it, but the handler should 403 it too |

### Backtest / Performance
| Element | State | Notes |
|---|---|---|
| Page exists with charts | ✅ | `features/backtest/` (equity-curve, return-comparison, outcome-distribution) — closest match to its mockup |
| KPI strip (win rate / total return / max DD / Sharpe / # trades) vs benchmark | 🟡 | confirm all five render with benchmark comparison + sparklines |
| Equity curve: Strategy vs Matched Buy-and-Hold + hover tooltip | 🟡/✅ | comparison chart exists; confirm dual-line + tooltip parity |
| Drawdown area chart sharing x-axis | 🟡 | confirm present |
| %/$ toggle | 🟡 | likely net-new |
| Results table sortable + paginated + export | 🟡 | confirm sort/paginate; export likely net-new |

---

## How to use this doc

1. When starting frontend work, open this file first to see the target and the gap.
2. Pick a 🟡/🔴 cluster (e.g. "decisions list sidebar + filters", "execution-leg
   table", "run/date switcher"). Treat each as its own slice: brainstorm → spec →
   plan → build.
3. **Resolve 🔴 items at the backend boundary before building their UI.** Several
   mockup columns (Edge BP, Confidence, Company name, Earnings date, Key drivers,
   option legs, "Needs Attention" status) require fields that the current
   `prescient_storage` payloads may not contain. Confirm the data exists (or add
   it server-side) before rendering it — never invent shapes in the frontend
   (this is the core "surface backend inconsistency, don't absorb it" rule).
4. Keep the shared design-language invariants (top of this doc) intact in every
   slice.

## Known functional findings (carried from review, not yet fixed)
- **Decision-list silent parse fallback** — `parse-decision-list.ts` swallows Zod
  failures into `{}` and renders "unknown"; should surface a loud malformed row
  (the mockup's BADROW treatment is the intended fix).
- **`live` not rejected at the mode-authorization route handler** — add a 403
  guard server-side in addition to the existing UI/client exclusion.
