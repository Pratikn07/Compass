import type { JournalRecordRow } from "@/features/decisions/decision-chain.types";

export const sourceCitation = {
  citation_id: "citation-1",
  provider: "finnhub",
  source_type: "earnings_release",
  title: "Peer earnings release",
  url: "https://example.test/peer-earnings",
  source_endpoint: "/stock/earnings",
  source_id: "PSTG:2026-Q1",
  as_of: "2026-06-01",
  retrieved_at: "2026-06-01T13:00:00Z",
  excerpt: "Peer earnings release cited stronger enterprise storage demand.",
  confidence: "high",
};

export const auditTrail = {
  source_citations: [sourceCitation],
  citation_unavailable_reasons: [],
  rule_facts: [
    {
      rule_name: "liquidity_gate",
      passed: true,
      observed_value: "sufficient",
      citation_ids: ["citation-1"],
    },
  ],
};

export const candidateBrief = {
  target: "NTNX",
  theme: "AI_STORAGE",
  earnings_date: "2026-06-03",
  report_time: "after_close",
  direction: "bullish",
  peer_signal_score: 0.82,
  positive_peer_ratio: 0.75,
  reported_peers: ["PSTG", "DELL"],
  peer_scores: [
    {
      ticker: "PSTG",
      score: 0.8,
      positive_factors: ["AI storage demand"],
      negative_factors: [],
      missing_factors: [],
    },
  ],
  main_thesis: "AI storage demand supports NTNX into earnings.",
  supporting_evidence: ["Peer reports cited stronger enterprise storage demand."],
  contradictions: [],
  recommended_expression: "defined-risk bullish call spread",
  technical_indicators: null,
  strategy_status: "candidate_ready_for_analyst",
  peer_summaries: [],
  source_citations: [sourceCitation],
};

export const strategyPayload = {
  thesis: "Bullish AI_STORAGE read-through for NTNX.",
  decision_summary: "candidate_ready_for_analyst",
  strategy_decision: {
    status: "candidate_ready_for_analyst",
    candidate: candidateBrief,
    rejection_reasons: [],
    rejection_details: [],
    audit: {},
    claude_analysis_allowed: true,
    audit_trail: auditTrail,
  },
  candidate_brief: candidateBrief,
  rejection_reasons: [],
  rejection_details: [],
  warnings: [],
  data_snapshot: {},
  settings_snapshot: {},
  missing_data: [],
  source_events: [],
};

export const analystPayload = {
  claude_result: {
    status: "analyzed",
    analysis: {
      recommendation: "support",
      thesis: "The setup is plausible but still advisory.",
      reasoning: "The peer signal supports a pre-earnings proposal.",
      conviction_score: 0.68,
      missing_context: [],
      contradictions: [],
      suggested_expression: "defined-risk bullish call spread",
      cited_citation_ids: ["citation-1"],
    },
    error_message: null,
    audit_trail: auditTrail,
  },
  status: "analyzed",
  analysis: {
    recommendation: "support",
    thesis: "The setup is plausible but still advisory.",
    reasoning: "The peer signal supports a pre-earnings proposal.",
    conviction_score: 0.68,
    missing_context: [],
    contradictions: [],
    suggested_expression: "defined-risk bullish call spread",
    cited_citation_ids: ["citation-1"],
  },
  error_message: null,
};

export const riskPayload = {
  risk_gate_decision: {
    target: "NTNX",
    theme: "AI_STORAGE",
    strategy_status: "candidate_ready_for_analyst",
    status: "risk_passed",
    rejection_reasons: [],
    explanation: "Risk gates passed for a propose-only defined-risk setup.",
    broker_execution_allowed: false,
    claude_present: true,
    claude_override_attempted: false,
    audit_trail: auditTrail,
  },
  status: "risk_passed",
  rejection_reasons: [],
  broker_execution_allowed: false,
};

export const positionSizingPayload = {
  position_sizing_decision: {
    status: "sized",
    target: "NTNX",
    theme: "AI_STORAGE",
    strategy_status: "candidate_ready_for_analyst",
    expression: "defined-risk bullish call spread",
    account_equity: 100000,
    risk_budget: 1000,
    unit_max_loss: 250,
    approved_quantity: 4,
    projected_max_loss: 1000,
    entry_cost_required: 980,
    rejection_reasons: [],
    warnings: [],
    explanation: "Code sizing capped quantity by risk budget.",
    claude_present: true,
    claude_sizing_override_attempted: false,
    audit_trail: auditTrail,
  },
  status: "sized",
  approved_quantity: 4,
  projected_max_loss: 1000,
  entry_cost_required: 980,
  rejection_reasons: [],
};

export const executionPayload = {
  proposal_status: "proposed",
  order_intent: "read_only_display",
  legs: [
    {
      side: "long",
      symbol: "NTNX 2026-06-19 55C",
      quantity: 4,
    },
  ],
};

export const outcomePayload = {
  outcome: {
    outcome_type: "pending",
    net_realized_pnl: null,
    gross_realized_pnl: null,
    fees: null,
    pnl_currency: "USD",
    open_quantity: 4,
    closed_quantity: 0,
    outcome_reasons: ["Position still open."],
    ambiguous: false,
  },
};

export function journalRow(
  overrides: Partial<JournalRecordRow> = {},
): JournalRecordRow {
  return {
    created_at: "2026-06-01T14:30:00Z",
    decision_id: "decision-1",
    decision_index: 0,
    duplicate_of_record_id: null,
    execution_mode: "propose_only",
    journal_record_id: "journal-1",
    order_id: null,
    parent_record_id: null,
    payload: strategyPayload,
    provider: null,
    record_type: "strategy_decision",
    run_id: "scheduled:2026-06-01",
    schema_version: 1,
    source: "strategy_engine",
    strategy_status: "candidate_ready_for_analyst",
    strategy_type: "bullish_earnings_readthrough",
    target: "NTNX",
    theme: "AI_STORAGE",
    trading_date: "2026-06-01",
    ...overrides,
  };
}
