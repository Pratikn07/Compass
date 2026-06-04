# Operator Mode State → Supabase — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorming), pending implementation plan
**Scope:** Move the FastAPI operator service's **execution-mode** state from a local
JSON file (`.prescient/execution-mode.json`) into Supabase, so the service survives
restarts/redeploys on an always-on host (Railway). Kill-switch state is explicitly
out of scope (separate follow-up).

**Why:** On a serverless/container host the local filesystem is ephemeral. The
current file-backed mode state would silently reset on every restart — unacceptable
for a system whose identity is code-owned, auditable trading rails. This is the one
backend change blocking a reliable always-on deployment.

---

## Guiding safety principle

**Any uncertainty resolves to `propose_only`, never to a more permissive mode.**
Every fail-safe in the current file implementation is preserved bit-for-bit; the
refactor changes only *where the latest record comes from*, not the interpretation
logic or the rails.

---

## 1. Architecture & the storage seam

The mode-authorization *logic* (rejection rules, propose-only/refuse-live defaults,
env precedence) is unchanged. Only persistence is abstracted behind a protocol.

```
mode_authorization.py  (logic — unchanged rules)
        │ depends on
        ▼
ModeStateStore (Protocol)        read_latest_accepted() -> ModeAuthorizationResult | None
   ├── FileModeStateStore        append_accepted(result) -> None
   │     current file behavior; tests + local dev
   └── SupabaseModeStateStore
         prod; reads/writes prescient_storage.operator_mode_authorizations
```

- **New module:** `src/prescient/operator/mode_state_store.py` — holds the `Protocol`
  plus both implementations (one focused file; mirrors how `prescient.storage`
  abstracts behind interfaces).
- `read_operator_status` and `authorize_execution_mode` gain an optional
  `store: ModeStateStore | None` parameter. When `None`, a factory selects the
  default **from env**:
  - `SUPABASE_URL` **and** `SUPABASE_SERVICE_ROLE_KEY` present → `SupabaseModeStateStore`
  - otherwise → `FileModeStateStore` (so tests + local dev need **zero DB**)
- `create_app` in `operator/api.py` already accepts `env` / `mode_path`; it passes
  through to store selection so existing wiring and the `mode_path` test seam keep
  working (when a `mode_path` is supplied, the file store is used).

**Interface contract (both implementations must satisfy):**
- `read_latest_accepted() -> ModeAuthorizationResult | None` — the newest accepted
  authorization, or `None` if there is none / state is unreadable.
- `append_accepted(result: ModeAuthorizationResult) -> None` — persist a newly
  accepted authorization. Raises on persistence failure (no silent success).

---

## 2. Data model & migration

New append-only table in the existing schema:

```sql
create table prescient_storage.operator_mode_authorizations (
    id                bigint generated always as identity primary key,
    status            text not null,              -- accepted | rejected (we persist accepted only)
    requested_mode    text not null,
    previous_mode     text not null,
    active_mode       text not null,
    actor             text not null,
    reason            text not null,
    rejection_reasons jsonb not null default '[]'::jsonb,
    warnings          jsonb not null default '[]'::jsonb,
    created_at        timestamptz not null default now(),
    schema_version    integer not null default 1
);
create index on prescient_storage.operator_mode_authorizations (created_at desc);

alter table prescient_storage.operator_mode_authorizations enable row level security;
grant usage on schema prescient_storage to service_role;   -- already granted; harmless
grant all on prescient_storage.operator_mode_authorizations to service_role;
-- No authenticated/anon policy: operator mode state is reachable ONLY through the
-- guarded FastAPI routes, never browser->Supabase directly. This is stricter than
-- the read tables, and correct for the rails.
```

- **Current mode = newest row.** Read = `order by created_at desc limit 1`, then run
  through the *same* interpretation: accepted? not live? → use `active_mode`; else
  `propose_only`.
- **Append-only:** `authorize_execution_mode` inserts a new row on each accepted
  authorization (insert, not upsert) → real audit trail of mode changes.
- **Accepted-only writes** (matches file behavior). The `status` column is present so
  rejected-attempt auditing is a clean future addition without a schema change.
- Migration file: `supabase/migrations/<timestamp>_operator_mode_authorizations.sql`.
  Applied to the hosted project as part of Phase 1.

---

## 3. Error handling & safety-critical fallback

- **Supabase read fails** (network/table-missing/malformed/auth): the store catches
  it and returns `None`; `read_operator_status` appends a warning
  (`"operator mode state unreadable: <reason>"`) and returns `propose_only` /
  source `default`. A DB outage can **never** silently leave the system in
  paper/live — it fails safe to the most conservative mode (mirrors the file path's
  `except → propose_only`).
- **Supabase write fails** during `authorize_execution_mode`: `append_accepted`
  raises; the authorization is **not** reported as durably accepted. The FastAPI
  route surfaces the error rather than claiming a mode change that did not persist.
- **`live` refusal unchanged:** `_mode_rejection_reasons` still rejects `live` unless
  `allow_live=True` **and** confirmation text matches. On read, any record with
  `active_mode == live` is still coerced to `propose_only` (the existing guard moves
  with the logic).
- **Env precedence preserved:** `PRESCIENT_EXECUTION_MODE` still overrides stored
  state and still refuses `live`.

Net: where the latest record comes from changes; every fail-safe
(→ `propose_only`, refuse-`live`, env precedence) is preserved.

---

## 4. Testing

TDD throughout. No live-Supabase calls in the suite — file store or fake client only;
CI stays DB-free and fast.

- **Existing tests pass untouched.** They pass `mode_path=tmp_path` → routed to
  `FileModeStateStore` by the default factory. This is the regression safety net
  proving behavior is preserved.
- **Shared `ModeStateStore` contract tests** run against *both* implementations:
  - append-then-read returns the just-written accepted authorization
  - newest row wins across multiple appends
  - empty store → `read_latest_accepted()` returns `None`
- **`SupabaseModeStateStore` unit tests** with a fake Supabase client (the codebase's
  existing fake-client pattern):
  - read failure → returns `None` (→ `propose_only` fail-safe), records unreadable
  - write failure → raises (no silent success)
  - stored `active_mode=live` row → coerced to `propose_only` on read
- **Logic tests** for `authorize_execution_mode` / `read_operator_status` run against
  an in-memory store to confirm rejection rules, env precedence, and live refusal are
  identical regardless of backend.
- **Frontend `operator-routes.test.ts`** unaffected (mocks the fetch boundary).

---

## 5. Out of scope (YAGNI)

- Kill-switch state migration (stays file-based; separate follow-up).
- Rejected-attempt persistence (schema supports it; not written yet).
- Any change to the mode-authorization rules, the `live` confirmation flow, or the
  frontend.
- Browser/`authenticated` direct access to operator mode state (intentionally none).

---

## 6. Definition of done

- `operator_mode_authorizations` table migration applied to hosted Supabase.
- `ModeStateStore` protocol + `FileModeStateStore` + `SupabaseModeStateStore` exist,
  env-selected by default.
- `authorize_execution_mode` / `read_operator_status` persist via the store; all
  fail-safes preserved.
- New contract + fake-client tests pass; **all previously-passing tests still pass**.
- FastAPI service, when given Supabase env, reads/writes mode state in Supabase and
  survives a restart (state persists).
