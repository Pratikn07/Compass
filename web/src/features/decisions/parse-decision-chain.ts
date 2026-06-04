import {
  AnalystReviewPayloadSchema,
  ExecutionProposalPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  SourceCitationSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "./decision-chain-schemas";
import {
  type DecisionChainRecord,
  type DecisionChainRecordType,
  type JournalRecordRow,
  type PayloadParseResult,
  type SourceCitation,
} from "./decision-chain.types";
import { CHAIN_STEP, isDecisionChainRecordType } from "./decision-chain-format";

export function parseDecisionChain(rows: JournalRecordRow[]): DecisionChainRecord[] {
  return rows
    .filter((row) => isDecisionChainRecordType(row.record_type))
    .map((row) => {
      const recordType = row.record_type as DecisionChainRecordType;
      const step = CHAIN_STEP[recordType];
      return {
        row,
        recordType,
        label: step.label,
        order: step.order,
        payload: parsePayload(recordType, row.payload),
      };
    })
    .sort((a, b) => {
      if (a.order !== b.order) return a.order - b.order;
      return String(a.row.created_at).localeCompare(String(b.row.created_at));
    });
}

function parsePayload(
  recordType: DecisionChainRecordType,
  raw: unknown,
): PayloadParseResult {
  const schema = schemaFor(recordType);
  const result = schema.safeParse(raw);
  if (!result.success) {
    return {
      ok: false,
      error: `Decision ${recordType} payload did not match expected shape: ${result.error.message}`,
      raw,
    };
  }

  return {
    ok: true,
    data: result.data,
    citations: extractCitations(recordType, result.data),
  };
}

function schemaFor(recordType: DecisionChainRecordType) {
  switch (recordType) {
    case "strategy_decision":
      return StrategyDecisionPayloadSchema;
    case "analyst_review":
      return AnalystReviewPayloadSchema;
    case "risk_decision":
      return RiskDecisionPayloadSchema;
    case "position_sizing":
      return PositionSizingPayloadSchema;
    case "execution_proposal":
      return ExecutionProposalPayloadSchema;
    case "trade_outcome":
    case "outcome_correction":
      return TradeOutcomePayloadSchema;
  }
}

function extractCitations(
  recordType: DecisionChainRecordType,
  data: unknown,
): SourceCitation[] {
  const citations: unknown[] = [];

  if (recordType === "strategy_decision") {
    const payload = StrategyDecisionPayloadSchema.parse(data);
    citations.push(
      ...payload.strategy_decision.audit_trail.source_citations,
      ...(payload.candidate_brief?.source_citations ?? []),
    );
  }

  if (recordType === "analyst_review") {
    const payload = AnalystReviewPayloadSchema.parse(data);
    citations.push(...payload.claude_result.audit_trail.source_citations);
  }

  if (recordType === "risk_decision") {
    const payload = RiskDecisionPayloadSchema.parse(data);
    citations.push(...payload.risk_gate_decision.audit_trail.source_citations);
  }

  if (recordType === "position_sizing") {
    const payload = PositionSizingPayloadSchema.parse(data);
    citations.push(
      ...payload.position_sizing_decision.audit_trail.source_citations,
    );
  }

  const unique = new Map<string, SourceCitation>();
  for (const citation of citations) {
    const parsed = SourceCitationSchema.safeParse(citation);
    if (parsed.success) {
      unique.set(parsed.data.citation_id, parsed.data);
    }
  }
  return [...unique.values()];
}
