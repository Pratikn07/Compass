# Prescient Backend Data Contract Audit

**Date:** 2026-06-04
**Status:** Audit complete; backend/UI follow-up required
**Source target:** `docs/superpowers/specs/2026-06-03-prescient-frontend-visual-target-and-gap-analysis.md`

## Purpose

This audit maps frontend mockup fields that are blocked on backend data to the
contracts that exist today. It does not change Supabase schema, backend payloads,
or UI rendering. The goal is to prevent the frontend from inventing shapes and to
make the next slices explicit.

Availability meanings:

- **Available now**: a stable table column or parsed payload field already exists
  and is already consumed by the frontend.
- **Available with parser/query work**: the backend writes enough data today, but
  frontend query/parsing/view-model work is still needed.
- **Backend change required**: the current backend does not expose a stable
  contract for the mockup field.

| Availability | Use in this audit |
|---|---|
| Available now | Stable and already consumed by the frontend. |
| Available with parser/query work | Backend data exists, but frontend mapping is still needed. |
| Backend change required | Backend must expose or define the contract first. |

## Contract Matrix

| UI target | Current source table/payload | Backend writer/model evidence | Frontend parser evidence | Availability | Recommended next action |
|---|---|---|---|---|---|
| Company name | None in `decision_records`, `journal_records`, or strategy payload | `CandidateBrief` stores `target`, not issuer/company name | No decision-list or chain schema maps company name | Backend change required | Add issuer metadata to a backend-owned payload or denormalized column before adding the rich table column. |
| Earnings date | `decision_records.payload.candidate_brief.earnings_date`; also `payload.data_snapshot.earnings_date` | `CandidateBrief.earnings_date` and `build_strategy_decision_record` write it | `StrategyDecisionPayloadSchema` parses it for chain; list parser does not expose it | Available with parser/query work | Add a list view-model field from `candidate_brief.earnings_date`; keep parse errors loud. |
| Edge BP | None | Backtest reports have returns/PnL metrics; strategy payload has `peer_signal_score`, not edge basis points | No schema maps an edge basis-point field | Backend change required | Define the financial edge metric backend-side before adding KPI strip, min-edge filter, or Edge BP column. |
| Confidence | Citation `confidence` and analyst `conviction_score` exist, but no list-level trade confidence exists | `ClaudeStrategyAnalysis.conviction_score` is analyst certainty; citations have evidence confidence | Chain schemas parse analyst/citation values; decision list has no confidence contract | Backend change required | Product must define confidence semantics. Do not treat citation confidence or analyst conviction as trade-outcome confidence unless product explicitly chooses that later. |
| Key drivers | `candidate_brief.supporting_evidence`, `candidate_brief.peer_scores`, and theme config drivers exist; no `key_drivers` field exists | `CandidateBrief.supporting_evidence` and `PeerScore` are written by strategy output | Chain schema parses supporting evidence and peer scores; list parser does not expose a key-driver view model | Available with parser/query work | Use `supporting_evidence` for the first rich table version, or add a backend `key_drivers` field if product wants a curated shorter list. |
| Option legs | `payload.data_snapshot.options_chain_summary` has ticker, option type, expiration, bid, ask, open interest only | `OptionContractSnapshot` has no strike; execution proposal accepts arbitrary `dict` payload | `ExecutionProposalPayloadSchema` is generic JSON, not structured option legs | Backend change required | Define an execution proposal/option leg model with side, quantity, type, expiry, strike, IV, price/credit, max loss, and breakevens. |
| Engine health | None as a single stable signal | Operator status exposes mode/kill switch; runs/provider tables expose symptoms, not health | Runs schemas parse runs, provider errors, and storage audit only | Backend change required | Add explicit operator/engine health signal or health endpoint before rendering "Engine Healthy". |
| Watchlists | None | Strategy universe config has theme/ticker sets, but no user/watchlist storage contract | No frontend schema or query for watchlists | Backend change required | Decide whether watchlists are config-derived theme groups or user-managed data, then expose a backend contract. |
| System status health | `runs`, `provider_errors`, `storage_write_audit`, and operator status can support partial operational status | Storage tables and operator status are already written/read | `runRowSchema`, `providerErrorRowSchema`, `storageAuditRowSchema`, and operator schemas exist | Available with parser/query work | Build derived status cards from existing tables first; add backend health signals only for Market Data/Pricing/Risk health that cannot be inferred. |
| Needs attention | None as a status enum or payload field | `StrategyStatus` has `no_trade`, `candidate_ready_for_analyst`, `rejected_with_reason`; risk/sizing have their own statuses | Decision list formatter has no `needs_attention` contract | Backend change required | Define whether this is a derived frontend bucket or backend status before adding filters/counts. |

## Current Usable Fields

The representative strategy journal payload already exposes these fields:

- `candidate_brief.earnings_date`
- `candidate_brief.peer_signal_score`
- `candidate_brief.supporting_evidence`
- `candidate_brief.peer_scores`
- `data_snapshot.option_contract_count`
- `data_snapshot.options_chain_summary` with `ticker`, `option_type`,
  `expiration_date`, `bid`, `ask`, and `open_interest`

These are suitable for parser/query work, but only after the frontend explicitly
maps them into view-model fields and keeps malformed payload handling loud.

## Not Stable Contracts Yet

The current representative strategy/list payload does not expose:

- `company_name`
- `edge_bp`
- `needs_attention`
- list-level `confidence`
- `key_drivers` as a named backend field
- full option-leg fields: `strike`, `side`, `iv`, `price`, `credit`,
  `breakeven`, `breakevens`

These require either a backend payload/table change or a product decision that
maps an existing field to the mockup label.

## Recommended Slice Order

1. **Parser/query-only slice:** expose earnings date and supporting evidence in
   decision list view models, using existing `candidate_brief` fields.
2. **Backend metric slice:** define edge BP and list-level confidence semantics.
3. **Execution proposal contract slice:** replace generic execution proposal JSON
   with a typed option-leg/proposal model.
4. **Operator health slice:** add explicit engine health only where existing runs,
   provider errors, storage audit, and operator status cannot answer the UI need.
