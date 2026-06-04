import {
  DecisionListPayloadSchema,
  type DecisionListPayload,
} from "./decision-list-schemas";
import type { DecisionListItem, DecisionRecordRow } from "./decision-list.types";

export function parseDecisionList(rows: DecisionRecordRow[]): DecisionListItem[] {
  return rows.map((row) => {
    const result = DecisionListPayloadSchema.safeParse(row.payload ?? {});

    // Surface backend inconsistency loudly — never absorb it into a benign row.
    if (!result.success) {
      return {
        decisionId: row.decision_id,
        runId: row.run_id,
        decisionIndex: row.decision_index,
        tradingDate: row.trading_date,
        target: row.target ?? "UNKNOWN",
        theme: row.theme ?? null,
        strategyType: row.strategy_type,
        status: "malformed",
        outcome: "malformed",
        mode: row.execution_mode,
        thesis: null,
        malformed: true,
        rawPayload: formatJson(row.payload),
      };
    }

    const parsedPayload: DecisionListPayload = result.data;
    const status =
      row.strategy_status ?? parsedPayload.decision_summary ?? "unknown";

    return {
      decisionId: row.decision_id,
      runId: row.run_id,
      decisionIndex: row.decision_index,
      tradingDate: row.trading_date,
      target: row.target ?? parsedPayload.candidate_brief?.target ?? "UNKNOWN",
      theme: row.theme ?? parsedPayload.candidate_brief?.theme ?? null,
      strategyType: row.strategy_type,
      status,
      outcome: deriveListOutcome(status, parsedPayload.outcome_type),
      mode: row.execution_mode,
      thesis:
        parsedPayload.thesis ??
        parsedPayload.candidate_brief?.main_thesis ??
        null,
      malformed: false,
      rawPayload: null,
    };
  });
}

function deriveListOutcome(status: string, explicitOutcome?: string): string {
  if (explicitOutcome) return explicitOutcome;
  const normalized = status.toLowerCase();
  if (normalized.includes("rejected") || normalized === "no_trade") {
    return "no_trade";
  }
  return "pending";
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? String(value);
}
