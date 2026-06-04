# PRD: R6.4 Storage: Supabase

## Ownership

Owner: Ours

Source note: Requirement from Ours: add Supabase as the durable storage backend for Prescient journals, learning inputs, provider snapshots, broker lifecycle events, and future operational reporting.

## Objective

Add a Supabase-backed storage layer that can persist and query the system's journal-safe records without changing hot-path strategy, risk, broker, or data-provider behavior.

R6.4 answers:

```text
Where should Prescient durably store decisions, lifecycle events, learning records, provider evidence, and operational audit data so the system can query them across runs?
```

Supabase storage is persistence infrastructure only. It must not make strategy decisions, place trades, run learning analysis, call Claude, or replace the existing deterministic models.

## Background

R6.1 defines an append-only decision journal. R6.2 defines a morning learning loop that reads prior journal records and produces bounded learning reports. The current runtime can write JSONL pipeline events, which is useful for local tests and MVP operation, but it is not enough for long-lived queryability, dashboards, multi-run learning windows, or operational audits.

R6.4 introduces Supabase as the durable storage backend behind a storage interface. Local JSONL remains a supported fallback and test fixture path. Supabase must store normalized, journal-safe records and preserve enough provenance for later learning, review, and reconciliation.

Supabase-specific security requirements are important because tables in exposed schemas can be reachable through Supabase APIs when roles have access. Any exposed table must use RLS, policies must use role-specific `TO` clauses, and service-role credentials must never be exposed to public clients.

Sources:

- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase Securing Your API](https://supabase.com/docs/guides/api/securing-your-api)
- [Supabase Storage Access Control](https://supabase.com/docs/guides/storage/security/access-control)
- [Supabase CLI Reference](https://supabase.com/docs/reference/cli/introduction)
- [Supabase MCP Setup](https://supabase.com/docs/guides/getting-started/mcp)

## Functional Requirements

### R6.4.1 Storage Boundary

Supabase storage must live behind a storage package or adapter boundary such as `prescient.storage`.

The following packages must not import Supabase clients or write directly to Supabase:

- `prescient.signal`
- `prescient.risk`
- `prescient.broker`
- `prescient.data`
- `prescient.analyst`

Those packages may return journal-safe models. Runtime, scheduler, learning, or a dedicated storage service owns persistence.

### R6.4.2 Storage Interface

The storage layer must expose provider-neutral interfaces for:

- Appending journal records.
- Reading journal records by date range, run ID, decision ID, target, theme, strategy type, and record type.
- Persisting run metadata and runtime summaries.
- Persisting data-provider snapshots and provider errors.
- Persisting broker order/fill/outcome lifecycle events.
- Persisting learning reports and settings-overlay proposals.
- Performing idempotent writes for records with deterministic IDs.

Local JSONL and Supabase implementations must satisfy the same interface where practical, so R6.1/R6.2 tests can run without requiring a live Supabase project.

### R6.4.3 Supabase Data Model

The Supabase schema must preserve append-only journal semantics.

Minimum logical tables:

- `runs`: one row per scheduled, manual, event-driven, broker, or learning run.
- `journal_records`: append-only normalized records keyed by `journal_record_id`.
- `decision_records`: indexed projection of strategy decision records for query speed.
- `lifecycle_records`: risk, sizing, proposal, order, fill, exit, and outcome records.
- `provider_snapshots`: normalized data-provider outputs and provenance references.
- `provider_errors`: journal-safe data-provider errors.
- `learning_reports`: R6.2 learning summaries, diagnostics, and parameter proposals.
- `storage_write_audit`: storage write attempts, idempotency keys, and failure diagnostics.

Raw provider payloads, raw transcripts, API keys, request headers, broker secrets, account identifiers, and unrestricted stack traces must not be stored.

### R6.4.4 Record Identity and Idempotency

Every persisted record must include:

- `journal_record_id`
- `record_type`
- `run_id`
- `decision_id`, when applicable
- `created_at`
- `trading_date`, when applicable
- `source`
- `payload`
- `schema_version`

Writes must be idempotent on stable record IDs. Re-running a pipeline with the same deterministic record IDs must not create duplicate journal rows. Later lifecycle changes must append new records rather than mutating earlier records.

### R6.4.5 Queryability

The storage layer must support read paths required by R6.1/R6.2:

- Read all records for a trading date.
- Read a rolling lookback window for learning.
- Read records for one run.
- Read all lifecycle records for one decision.
- Read unresolved or pending outcomes.
- Read realized outcomes by target, theme, strategy type, and date range.
- Read provider errors by provider, ticker, and date range.
- Read learning reports and applied/declined parameter proposals.

Queries must return normalized models, not raw Supabase response dictionaries.

### R6.4.6 Security and Access Control

Supabase must be configured with a private-by-default posture.

Required security behavior:

- Use server-side environment variables only for Supabase service-role or secret keys.
- Never expose service-role or secret keys to browser/public clients.
- Prefer a private schema for internal trading/journal tables.
- Enable RLS on every table in any exposed schema.
- Use policy `TO` clauses such as `TO authenticated` rather than deprecated `auth.role()` checks.
- Do not use `user_metadata` or `raw_user_meta_data` for authorization decisions.
- Avoid `SECURITY DEFINER` functions unless they are isolated in a non-exposed schema, tightly scoped, and explicitly justified.
- If views are exposed, use `security_invoker = true` on Postgres 15+ or revoke public access on older versions.

For MVP, Prescient backend services may use server-side credentials to write internal records. End-user dashboard access, if added later, must be mediated by explicit RLS policies and views.

### R6.4.7 Supabase Storage Buckets

Supabase file buckets are optional for R6.4.

If future work stores large artifacts such as full transcripts, rendered reports, or exported audit bundles, bucket access must:

- Store only non-secret artifacts.
- Use deterministic object paths.
- Preserve references in database rows.
- Use RLS/storage policies matched to the actual access model.
- Grant upsert only when INSERT, SELECT, and UPDATE permissions are intentionally supported.

The MVP database schema must not depend on bucket storage.

### R6.4.8 Migration and Deployment

Schema changes must be managed through Supabase migrations or an equivalent reviewed SQL migration flow.

Implementation must:

- Discover Supabase CLI commands with `supabase --help` before relying on them.
- Generate migrations through the configured Supabase workflow rather than hand-inventing timestamped filenames.
- Run Supabase advisors or equivalent checks before migration handoff.
- Keep local/test storage runnable without a remote Supabase project.
- Document required environment variables without committing secrets.

### R6.4.9 Failure Handling

Storage failures must return structured, journal-safe errors.

Required failure cases:

- Missing Supabase URL or key.
- Unauthorized or invalid credentials.
- RLS/policy rejection.
- Network timeout.
- Database unavailable.
- Duplicate record conflict with incompatible payload.
- Schema version mismatch.
- Malformed stored payload.
- Query window too large.

The runtime must be able to choose whether a storage failure is fatal. For hot-path trading safety, failure to persist required decision records should default to blocking live execution until the record can be written or the run is explicitly in a non-live mode.

### R6.4.10 Compatibility With JSONL

R6.4 must preserve compatibility with existing JSONL journals.

Expected behavior:

- Existing JSONL journal writer remains available for local tests and fallback operation.
- A future importer can backfill JSONL records into Supabase using stable IDs.
- Supabase reads can feed R6.2 learning through the same reader interface as JSONL.
- JSONL and Supabase serialization must be deterministic for the same journal-safe models.

## Acceptance Criteria

- A PRD exists for R6.4 Supabase storage with explicit storage boundary, schema concepts, security posture, migration requirements, and failure handling.
- Future implementation exposes a storage interface that can be backed by local JSONL or Supabase.
- Supabase writes are idempotent and append-only for lifecycle records.
- Supabase reads can retrieve records by run, decision, date range, target, theme, record type, and unresolved outcome status.
- Storage code does not leak Supabase clients into signal, risk, broker, data, or analyst packages.
- All persisted records are journal-safe and schema-versioned.
- Missing Supabase configuration and write/query failures return structured errors.
- RLS/security requirements are included for any exposed schema or dashboard-facing data.
- Existing runtime and learning tests can run without a live Supabase project.

## Non-Goals

- No live Supabase migration implementation in the PRD.
- No dashboard UI.
- No public client access to trading or journal tables.
- No strategy, risk, broker, or analyst behavior changes.
- No automatic learning loop changes beyond providing persistent records.
- No raw transcript or raw provider-payload storage unless a later artifact-storage milestone defines safe retention rules.
- No Supabase Edge Functions, Realtime, Auth, Cron, Queues, or Vectors unless required by a later milestone.

## Assumptions and Defaults

- Supabase primarily means Postgres-backed durable storage for Prescient records, not only Supabase file buckets.
- Local JSONL remains supported for tests and fallback.
- Internal write access uses server-side credentials only.
- Tables should live in a private schema unless a future dashboard requires a restricted exposed view.
- R6.4 is a storage foundation for R6.1/R6.2; it does not replace the deterministic hot path.
