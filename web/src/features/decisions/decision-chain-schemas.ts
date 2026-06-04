import { z } from "zod";

const JsonObjectSchema = z.record(z.string(), z.unknown());

export const SourceCitationSchema = z
  .object({
    citation_id: z.string().min(1),
    provider: z.string().min(1),
    source_type: z.string().min(1),
    title: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    source_endpoint: z.string().nullable().optional(),
    source_id: z.string().nullable().optional(),
    as_of: z.string().nullable().optional(),
    retrieved_at: z.string().nullable().optional(),
    excerpt: z.string().nullable().optional(),
    confidence: z.string().optional(),
  })
  .passthrough();

const RuleFactSchema = z
  .object({
    rule_name: z.string(),
    passed: z.boolean().nullable().optional(),
    threshold: z.union([z.string(), z.number(), z.boolean()]).nullable().optional(),
    observed_value: z
      .union([z.string(), z.number(), z.boolean()])
      .nullable()
      .optional(),
    reason: z.string().nullable().optional(),
    citation_ids: z.array(z.string()).default([]),
  })
  .passthrough();

export const AuditTrailSchema = z
  .object({
    source_citations: z.array(SourceCitationSchema),
    citation_unavailable_reasons: z.array(z.string()),
    rule_facts: z.array(RuleFactSchema),
  })
  .passthrough();

const RejectionDetailSchema = z
  .object({
    reason: z.string(),
    stage: z.string(),
    message: z.string(),
  })
  .passthrough();

const PeerScoreSchema = z
  .object({
    ticker: z.string(),
    score: z.number(),
    positive_factors: z.array(z.string()).default([]),
    negative_factors: z.array(z.string()).default([]),
    missing_factors: z.array(z.string()).default([]),
  })
  .passthrough();

const CandidateBriefSchema = z
  .object({
    target: z.string(),
    theme: z.string(),
    earnings_date: z.string(),
    report_time: z.string(),
    direction: z.string(),
    peer_signal_score: z.number(),
    positive_peer_ratio: z.number(),
    reported_peers: z.array(z.string()),
    peer_scores: z.array(PeerScoreSchema),
    main_thesis: z.string(),
    supporting_evidence: z.array(z.string()),
    contradictions: z.array(z.string()),
    recommended_expression: z.string(),
    technical_indicators: z.unknown().nullable(),
    strategy_status: z.string(),
    peer_summaries: z.array(z.unknown()),
    source_citations: z.array(SourceCitationSchema),
  })
  .passthrough();

export const StrategyDecisionPayloadSchema = z
  .object({
    thesis: z.string(),
    decision_summary: z.string(),
    strategy_decision: z
      .object({
        status: z.string(),
        candidate: CandidateBriefSchema.nullable(),
        rejection_reasons: z.array(z.string()),
        rejection_details: z.array(RejectionDetailSchema),
        audit: JsonObjectSchema,
        claude_analysis_allowed: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    candidate_brief: CandidateBriefSchema.nullable(),
    rejection_reasons: z.array(z.string()),
    rejection_details: z.array(RejectionDetailSchema),
    warnings: z.array(z.unknown()),
    data_snapshot: JsonObjectSchema,
    settings_snapshot: JsonObjectSchema,
    missing_data: z.array(z.string()),
    source_events: z.array(z.unknown()),
  })
  .passthrough();

const ClaudeStrategyAnalysisSchema = z
  .object({
    recommendation: z.string(),
    thesis: z.string(),
    reasoning: z.string(),
    conviction_score: z.number(),
    missing_context: z.array(z.string()),
    contradictions: z.array(z.string()),
    suggested_expression: z.string(),
    cited_citation_ids: z.array(z.string()),
  })
  .passthrough();

export const AnalystReviewPayloadSchema = z
  .object({
    claude_result: z
      .object({
        status: z.string(),
        analysis: ClaudeStrategyAnalysisSchema.nullable(),
        error_message: z.string().nullable(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    analysis: ClaudeStrategyAnalysisSchema.nullable(),
    error_message: z.string().nullable(),
  })
  .passthrough();

export const RiskDecisionPayloadSchema = z
  .object({
    risk_gate_decision: z
      .object({
        target: z.string(),
        theme: z.string().nullable(),
        strategy_status: z.string(),
        status: z.string(),
        rejection_reasons: z.array(z.string()),
        explanation: z.string(),
        broker_execution_allowed: z.boolean(),
        claude_present: z.boolean(),
        claude_override_attempted: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    rejection_reasons: z.array(z.string()),
    broker_execution_allowed: z.boolean(),
  })
  .passthrough();

export const PositionSizingPayloadSchema = z
  .object({
    position_sizing_decision: z
      .object({
        status: z.string(),
        target: z.string(),
        theme: z.string().nullable(),
        strategy_status: z.string(),
        expression: z.string().nullable(),
        account_equity: z.number().nullable(),
        risk_budget: z.number().nullable(),
        unit_max_loss: z.number().nullable(),
        approved_quantity: z.number(),
        projected_max_loss: z.number().nullable(),
        entry_cost_required: z.number().nullable(),
        rejection_reasons: z.array(z.string()),
        warnings: z.array(z.string()),
        explanation: z.string(),
        claude_present: z.boolean(),
        claude_sizing_override_attempted: z.boolean(),
        audit_trail: AuditTrailSchema,
      })
      .passthrough(),
    status: z.string(),
    approved_quantity: z.number(),
    projected_max_loss: z.number().nullable(),
    entry_cost_required: z.number().nullable(),
    rejection_reasons: z.array(z.string()),
  })
  .passthrough();

export const ExecutionProposalPayloadSchema = JsonObjectSchema;

export const DecisionOutcomeSchema = z
  .object({
    outcome_type: z.string(),
    net_realized_pnl: z.number().nullable(),
    gross_realized_pnl: z.number().nullable(),
    fees: z.number().nullable(),
    pnl_currency: z.string(),
    open_quantity: z.number().nullable(),
    closed_quantity: z.number().nullable(),
    outcome_reasons: z.array(z.string()),
    ambiguous: z.boolean(),
  })
  .passthrough();

export const TradeOutcomePayloadSchema = z
  .object({
    outcome: DecisionOutcomeSchema,
  })
  .passthrough();
