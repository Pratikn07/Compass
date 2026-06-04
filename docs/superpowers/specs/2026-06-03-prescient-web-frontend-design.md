# Prescient Web Frontend — Design

**Date:** 2026-06-03
**Status:** Approved (brainstorming), pending implementation plan
**Scope:** First web frontend for the `prescient` autonomous earnings read-through
options trading system. Desktop-first. Built in vertical slices, not horizontal
layers.

---

## 1. Guiding principle

Build in **vertical slices**, not horizontal layers. Pick one feature, build it
all the way through — screen → typed data → loading/error/empty states →
navigation → working against the real backend — ship it, review it, merge it,
then move to the next. Each slice is a small, complete, testable thing.

The frontend is a **thin presentation layer over a decision-review /
observability surface.** It is NOT a trading terminal. Logic lives in the Python
engine; the UI renders state and, for a tiny set of guarded actions, sends a
request that the code rails enforce.

---

## 2. Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| API boundary | **Hybrid (C):** frontend reads Supabase directly; guarded actions go through a Python endpoint behind a Next route handler |
| Platform | **Web app (Next.js), desktop-first.** First and only build for now |
| Core loop | **Decision review (A):** "what did the engine propose today, and why" |
| Users | **Single operator (A).** RLS: authenticated reads all of `prescient_storage` |
| Stack | **Approach 1:** Next.js App Router + shadcn/ui + Tailwind + TanStack Query + Supabase JS client + Zod payload parsers |

---

## 3. Hard frontend rules (mirror of CLAUDE.md)

These are non-negotiable and mirror the code-owned rails. They constrain the
design, not just the implementation.

1. The frontend **never** sizes, approves, or places a trade. There is **no buy
   button, ever.** (Mirrors Hard Rule 2.)
2. The frontend **never** calls Claude. Advisory reasoning is **read from the
   journal**, never generated client-side. (Mirrors Hard Rule 5.)
3. The frontend **never** writes to `prescient_storage`. It is read-only against
   the database. The only writes happen through the guarded Python action path.
4. The UI **never** sets, defaults to, or infers `live` mode. It displays
   whatever the data says. Mode transitions are human-authorized through code.
5. Position sizing is displayed **read-only**. It is never editable in the UI.

---

## 4. Architecture & boundaries

```
Browser (Next.js client)
   │
   ├── reads ──────────────► Supabase  (prescient_storage, RLS: authenticated reads all)
   │                            ▲
   │                            │ writes only
   │                     prescient (Python engine, service_role)
   │
   └── guarded actions ──► Next route handler ──► Python action endpoint
                            (holds secret,         (mode auth / kill switch —
                             server-side only)      goes THROUGH code rails)
```

Two deliberately asymmetric paths:

- **Read path:** browser → Supabase directly via the JS client + TanStack Query.
  The authenticated single operator reads all of `prescient_storage`. No business
  logic in the browser — it renders rows.
- **Action path:** anything that touches the rails (authorize a mode transition,
  arm/disarm kill switch) never goes browser→Supabase. It goes browser → Next
  route handler (server-side, holds the privileged secret) → Python action
  endpoint, which enforces the R-rules in code. The UI can *request* "promote to
  paper"; only code decides.

---

## 5. The thin shell (built once — the only upfront chunk)

Deliberately thin: everything later slices need, nothing they don't.

**Routing (Next App Router):**

```
/login                  → auth gate
/(app)                  → authenticated layout (nav + session guard)
  /                      → redirect to /decisions
  /decisions             → decision-review list   (core loop, slice 1)
  /decisions/[id]        → single decision chain   (slice 2)
  /runs                  → system status / runs    (slice 3)
  /backtest              → performance analytics    (slice 4)
```

**Auth + session:** Supabase Auth, single operator. Server-side session guard on
the `(app)` layout — unauthenticated → `/login`. Gates everything.

**Design-token foundation:** Tailwind config holding tokens — spacing scale,
type scale, and semantic color tokens (`success` / `danger` / `warning` /
`muted`) so a "risk rejected" reads red consistently everywhere. One source so
the design can't drift.

**Reusable primitives:** `Button`, `Input`, `Card`, `Badge` (statuses:
`propose_only`, `risk_blocked`, `proposed`, …), `Table`.

**Three state components — non-negotiable, every screen wires all three:**
`<LoadingState>`, `<ErrorState>`, `<EmptyState>`. `<ErrorState>` is designed to
surface a **parse/backend** error *loudly* ("decision payload didn't match
expected shape") rather than hide it.

**Data plumbing:** TanStack Query provider + a single configured Supabase
browser client, set up once, reused by every slice.

---

## 6. The decision-review slice (core loop)

### 6a. `/decisions` — the list

A run produces N `decision_records`. The list shows the latest run's decisions
(with a date/run switcher). Each row:

| Target | Theme | Strategy | Status | Outcome | Mode |
|--------|-------|----------|--------|---------|------|
| NVDA | AI Infra | bullish_earnings_readthrough | `proposed` | `pending` | `propose_only` |

Status/outcome render as semantic `Badge`s — `risk_blocked` red, `proposed`
green, `no_trade` muted. Loading/error/empty all wired (empty = "no run yet
today").

### 6b. `/decisions/[id]` — the chain (the actual product)

Render the `journal_records` for that `decision_id` as the system's boundary,
top to bottom — because that is exactly how the chain is stored:

```
1. strategy_decision   ── deterministic candidate brief
                            (target, theme, peer read-through evidence, why it triggered)
2. analyst_review      ── Claude's ADVISORY reasoning  ← labeled "advisory, not authorization"
3. risk_decision       ── PASS / REJECT + structured reasons  ← the rails, visually dominant
4. position_sizing     ── code-decided size (read-only; never editable)
5. execution_proposal  ── what would be placed (propose_only → proposed, not placed)
6. outcome             ── pending / filled / closed_win|loss, P&L if any
```

Each step is a `Card` showing its `source_citations` (R6.3 audit trail). The
`risk_decision` card is the visual anchor (green pass / red reject + reasons)
because in a propose-only system the rails are the story. The `analyst_review`
card carries explicit "advisory only" treatment so the UI never implies Claude
approved anything.

**No actions on these screens.** No buy, no approve, no edit-size. Pure
read-and-understand.

---

## 7. Data layer & payload typing (make backend mess loud)

Three layers between Supabase and the screen:

1. **Generated Supabase types (table-level).** Supabase codegen → exact types
   for `runs`, `decision_records`, `journal_records`, etc. The frontend never
   guesses table shapes; regenerate when the migration changes.

2. **Zod parsers (payload-level) — one per `record_type`.** The generated types
   only know `payload` is `jsonb`. The real content lives there, so we write one
   Zod schema per rendered record type, derived by reading the Python pydantic
   models that *write* them (`StrategyDecision`, `ClaudeAnalysisResult`,
   `RiskGateDecision`, `PositionSizingDecision`, etc.):
   - `StrategyDecisionPayload` → target, theme, peer_evidence[], trigger_reasons[]
   - `AnalystReviewPayload` → reasoning, confidence?, advisory: true
   - `RiskDecisionPayload` → passed, rejection_reasons[], review_flags[]
   - `PositionSizingPayload` → size, basis
   - `ExecutionProposalPayload` → proposal fields
   - `OutcomePayload` → outcome_type, net_realized_pnl?

3. **Parse boundary = error surface.** When a payload fails its Zod parse, the
   card renders `<ErrorState>` ("decision payload didn't match expected shape")
   with the raw blob in a details drawer — **never** blank or guessed. A
   malformed risk decision can never silently render as a benign card.

**Query organization (TanStack Query):** typed hooks, one per data need, each
returning parsed-or-error: `useLatestRun()`, `useDecisions(runId)`,
`useDecisionChain(decisionId)`. Caching + refetch handled by TanStack; light
refetch-on-focus so a new run appears when returning to the tab. No websockets —
a scheduled, propose-only system is well served by polling/refetch.

---

## 8. Backend changes required

The current migration enables RLS on `prescient_storage` tables but grants only
`service_role` with **no `select` policy for `authenticated`** — so authenticated
reads return nothing today. Slice 0 adds a migration creating an
authenticated-read `select` policy (`using (true)`) on each `prescient_storage`
table, consistent with "single operator reads all." This is the one backend
change the frontend work requires.

Supabase project provisioning, CLI link, and first type-gen are also **part of
slice 0** (not yet set up).

---

## 9. Build order (vertical slices)

Each slice is a complete, reviewed, merged unit before the next starts.

**Slice 0 — Shell + foundation** *(only upfront chunk)*
Provision Supabase project, link CLI, generate types. Add authenticated-read RLS
migration. Next App Router skeleton, Supabase Auth + session guard, Tailwind
tokens, primitives, three state components, TanStack Query + Supabase client.
**Done = log in and see an empty authenticated `/decisions`.**

**Slice 1 — Decision list (`/decisions`)**
`useLatestRun()` + `useDecisions(runId)`, table with semantic badges, run/date
switcher, loading/error/empty, Zod parsers for shown columns.
**Done = log in, see today's proposed decisions in a table against real data.**

**Slice 2 — Decision chain (`/decisions/[id]`)**
`useDecisionChain()`, the 6-step `record_type` chain as cards, risk card
dominant, analyst "advisory only" treatment, source citations, full payload Zod
parsers + loud parse-error surface.
**Done = click a decision, understand exactly what it proposed and why.**

> **Core loop is shippable after Slice 2.** Everything below is additive.

**Slice 3 — Runs / system status (`/runs`)**
Scheduler last-run, execution mode, daily-halt status, provider errors.
Introduces the **first guarded action**: mode-authorization request via Next
route handler → Python endpoint.

**Slice 4 — Backtest analytics (`/backtest`)**
Win rate, drawdown, Sharpe, P&L vs buy-and-hold from `learning_reports` /
backtest output. First charts.

**Later — Mobile alerts** — out of scope for this web build; revisit after
Slice 4.

**Per-slice agent instruction template:**
> "Build slice X end-to-end: the screen using our existing design primitives and
> tokens, data fetched through the typed hooks + Zod parsers (never inline fetch
> with guessed shapes), explicit loading / error / empty states, wired into
> navigation. Do not invent backend behavior — if a payload shape is missing or
> unclear, stop and tell me rather than guessing. One slice only; show me the
> running result."

---

## 10. Out of scope (YAGNI)

- No mobile app in this build.
- No websockets / live streaming (scheduled system; refetch suffices).
- No multi-user roles or per-row ownership (single operator).
- No trade entry, sizing, or approval UI of any kind.
- No client-side Claude calls.
- No write access to `prescient_storage` from the browser.
