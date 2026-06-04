# PRD: R6.3 Audit Trail / Source Citations on Every Decision

## Ownership

Owner: GPT

Source note: Requirement from GPT review: every decision must include an audit trail and source citations so the system can explain what data, rules, and evidence caused an approval, rejection, analysis, or execution outcome.

## Objective

Add a structured audit and citation layer so every strategy, analyst, risk, sizing, broker, learning, and journal decision can answer:

```text
What evidence and rules led to this decision, and where did that evidence come from?
```

R6.3 must make decisions replayable, reviewable, and source-attributable without exposing secrets, raw provider payloads, raw prompts, account identifiers, or broker credentials.

## Background

Earlier milestones already produce structured decision objects:

- `StrategyDecision` with rejection details and `DecisionAudit`.
- Runtime JSONL journal events for hot-path decisions, sub-agent reviews, and Claude analysis.
- Risk gate, position sizing, daily halt, execution-quality, account-size, and broker-preflight decisions.
- Data adapters with provider metadata, source endpoints, URLs, and journal-safe provider errors.
- Learning-loop PRD R6.2, which depends on prior journal records being trustworthy and interpretable.

Those pieces are useful, but they are not yet a complete evidence ledger. A future user reviewing a trade should not have to infer why the system acted from scattered fields. Every decision should carry compact citations and audit facts in one consistent shape.

## Definitions

### Decision

A structured output produced by any layer that approves, rejects, skips, blocks, sizes, analyzes, proposes, places, fills, cancels, exits, learns from, or otherwise evaluates a trading-related action.

Decision-producing layers include:

- Signal / strategy output.
- Analyst and sub-agent output.
- Event classification.
- Scheduler run requests and summaries.
- Runtime pipeline events.
- Risk gatekeeper.
- Position sizing.
- Daily halt.
- Account-size policy.
- Execution-quality gate.
- Broker preflight.
- Broker order/fill outcomes.
- Learning reports.

### Audit Trail

A deterministic, journal-safe record of the decision context:

- Decision identifier.
- Run identifier.
- Decision type and layer.
- Target ticker and theme, when applicable.
- Inputs used.
- Rules and thresholds applied.
- Pass/fail/rejection reasons.
- Data completeness indicators.
- Related upstream and downstream decision identifiers.
- Source citations supporting the decision.

### Source Citation

A compact structured reference to data or evidence used by a decision.

Expected citation fields:

```python
class SourceCitation(BaseModel):
    provider: str
    source_type: str
    title: str | None
    url: str | None
    source_endpoint: str | None
    source_id: str | None
    as_of: datetime | date | None
    retrieved_at: datetime | None
    excerpt: str | None
    confidence: str | None
```

The exact implementation may refine this shape, but every citation must remain bounded, structured, and safe for JSONL journaling.

### Evidence Bundle

A normalized collection of citations and compact facts attached to a decision.

Examples:

- Earnings calendar provider row.
- Peer earnings actual/surprise source.
- Price/indicator provider snapshot.
- News/sentiment article metadata.
- SEC filing accession and source URL.
- Transcript summary citation.
- Broker account/preflight snapshot reference.
- Risk rule and threshold reference.

## User Value

R6.3 gives the user:

- A clear explanation for every approval, rejection, skip, and block.
- Source-backed review of each candidate and trade.
- Easier debugging of bad data, bad assumptions, or provider drift.
- Safer use of Claude because analysis can be tied to structured cited evidence.
- Better learning-loop inputs because outcomes can be linked to the evidence used at decision time.
- A path toward compliance-style auditability without adding broker execution risk.

## Functional Requirements

### R6.3.1 Citation Coverage

Every decision object that can be journaled must include source citations or an explicit reason why citations are unavailable.

Required behavior:

- Candidate-ready strategy decisions must include citations for peer earnings evidence, target earnings calendar evidence, target market data, options liquidity, and indicator snapshots when those inputs are present.
- Rejected strategy decisions must include citations for any data that caused or supported the rejection, when available.
- Claude analyst and sub-agent outputs must cite the `CandidateBrief` they analyzed and may cite source citations already attached to the brief.
- Risk decisions must cite the structured risk inputs and rules used, such as account snapshot, order proposal, max-risk policy, sizing math, daily halt state, or execution-quality quote.
- Broker preflight and execution decisions must cite broker-provided snapshots and broker response references when available.
- Learning reports must cite prior journal records and decision identifiers, not raw unbounded payloads.

If a decision used no external source, it must include a citation equivalent to `source_type = "internal_rule"` or `source_type = "internal_config"` with the rule/config name.

### R6.3.2 Decision Identity and Linking

Every journaled decision must include stable identifiers suitable for joining records across the pipeline.

Required fields:

- `run_id`
- `decision_id`
- `decision_type`
- `decision_layer`
- `target`, when applicable
- `theme`, when applicable
- `parent_decision_ids`, when applicable
- `related_order_ids`, when applicable
- `related_event_ids`, when applicable

IDs must be deterministic when created from deterministic test inputs. Runtime may later add UUIDs or timestamps, but test fixtures must be able to supply stable IDs.

### R6.3.3 Citation Safety

Citations must be bounded and journal-safe.

They must not include:

- API keys.
- Authorization headers.
- Account numbers or account IDs.
- Raw provider payloads.
- Raw article bodies.
- Full earnings-call transcripts.
- Full SEC filings.
- Raw Claude prompts.
- Broker credentials.
- Unbounded stack traces.

Excerpt fields must be short enough for logs and prompts. Long source content must be represented by metadata, source URL, accession number, provider ID, or a bounded summary.

### R6.3.4 Decision Snapshot Integrity

The audit trail must preserve the rule and threshold values used at decision time.

Examples:

- Peer ratio threshold.
- Average peer score threshold.
- Minimum reported peer count.
- Target run-up threshold.
- Volume and liquidity thresholds.
- Max trade loss cap.
- Position sizing risk budget.
- Daily halt limits.
- Account-size policy thresholds.
- Broker mode.

Future changes to config defaults must not rewrite prior decision audit records.

### R6.3.5 Citation Propagation

Citations should flow forward with normalized inputs.

Examples:

- Data adapter snapshots produce citations.
- Signal engine consumes cited data and preserves citations on `StrategyDecision`.
- Runtime journals decisions with citations before Claude runs.
- Claude receives only bounded candidate/citation context that is already allowed for cold-path analysis.
- Risk and broker layers add their own citations without deleting prior strategy citations.
- Learning loop references decision IDs and citations instead of reinterpreting raw data.

Citation propagation must not create circular model imports. Provider-specific adapters should not be imported by `prescient.signal`, `prescient.risk`, or broker execution code.

### R6.3.6 Rejection Audit Requirements

Rejected decisions require especially clear audit trails.

Every rejected decision must include:

- Rejection reason.
- Rejection stage.
- Human-readable message.
- Rule or threshold that failed.
- Actual observed value when available.
- Citation for the observed value when available.
- Data missing reason when observed value is unavailable.

Rejected decisions must never silently omit why a candidate, risk proposal, or broker action was blocked.

### R6.3.7 Analyst Citation Requirements

Claude and sub-agents must not invent citations.

Required behavior:

- Analyst prompts may include bounded citations from the `CandidateBrief`.
- Analyst output must refer only to citation IDs or titles already supplied in the prompt.
- Any citation not present in the structured input must be rejected or marked unsupported.
- Claude output remains advisory and cannot modify deterministic audit facts.

### R6.3.8 Journal Writer Requirements

Journal records must preserve citations in JSON-safe form.

Required behavior:

- JSONL journal writes one complete decision/audit object per line.
- Citations must serialize deterministically in tests.
- Missing citation lists must serialize as empty lists or explicit unavailable reasons.
- Journal events must keep hot-path decisions before cold-path analyst results.
- Journal records must be readable by R6.2 learning loop without needing provider-specific raw payloads.

### R6.3.9 Replay and Review Requirements

It must be possible to reconstruct the decision chain from the journal alone.

For any final order or no-trade outcome, the user should be able to trace:

```text
event or schedule trigger
  -> data snapshots and citations
  -> strategy decision
  -> analyst/sub-agent decision, when enabled
  -> risk and sizing decisions
  -> broker preflight/execution decision, when applicable
  -> outcome and learning records, when available
```

Replay does not require refetching external provider data. The journal must hold enough cited metadata to explain what the system knew at the time.

## Non-Functional Requirements

### Determinism

The same structured inputs must produce the same serialized audit/citation output in tests.

### Source Independence

Citations must be provider-neutral. Adding or replacing Finnhub, FMP, Alpha Vantage, SEC EDGAR, Daloopa, Financial Datasets, Alpaca, or Robinhood must not require changing core citation consumers.

### Security

Audit records must never leak secrets or personally identifying account information.

### Compactness

Citations should remain compact. They are pointers and summaries, not copies of full source documents.

### Backward Compatibility

Older journal records that lack citations may still be readable. The reader should mark them as `citation_unavailable_legacy_record` rather than failing.

## Acceptance Criteria

- Every new decision type has either `source_citations` or a structured unavailable reason.
- Candidate-ready and rejected strategy decisions preserve evidence citations.
- Risk, sizing, execution-quality, daily halt, account-policy, broker, and learning outputs can cite internal rules/configs.
- Analyst outputs cannot introduce uncited external claims.
- Journal records serialize citations safely and deterministically.
- Serialized journal records contain no API keys, auth headers, account IDs, raw prompts, raw provider payloads, raw transcripts, or full filings.
- Boundary tests prove provider-specific adapters are not imported into deterministic core layers only to resolve citations.
- R6.2 learning records can reference cited decision IDs without refetching external data.

## Non-Goals

- No new broker execution.
- No new data provider integration.
- No full database schema migration in this PRD.
- No external compliance certification.
- No raw transcript, article, SEC filing, or provider-payload storage.
- No Claude permission to change deterministic audit facts.
- No automatic learning-loop parameter changes beyond R6.2 scope.

