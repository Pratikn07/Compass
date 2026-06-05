import {
  formatList,
  formatMoney,
} from "./decision-chain-format";
import type {
  AnalystReviewPayload,
  DecisionChainRecord,
  ExecutionProposalPayload,
  PositionSizingPayload,
  StrategyDecisionPayload,
  TradeOutcomePayload,
} from "./decision-chain.types";

export type DecisionChainViewModel = {
  header: {
    executionMode: string;
    outcome: string;
    runId: string;
    strategyStatus: string;
    target: string;
    theme: string;
  };
};

export type StrategyEvidenceViewModel = {
  contradictions: string[];
  direction: string;
  earningsDate: string;
  expression: string;
  peerSignalScoreLabel: string;
  peerScores: StrategyPeerScoreViewModel[];
  positivePeerRatioLabel: string;
  reportedPeersLabel: string;
  reportTime: string;
  status: string;
  supportingEvidence: string[];
  thesis: string;
};

export type StrategyPeerScoreViewModel = {
  missingFactorsLabel: string;
  negativeFactorsLabel: string;
  positiveFactorsLabel: string;
  scoreLabel: string;
  ticker: string;
};

export type AnalystReviewViewModel = {
  analystConvictionLabel: string;
  citedCitationIdsLabel: string;
  contradictionsLabel: string;
  missingContextLabel: string;
  reasoning: string | null;
  recommendation: string;
  suggestedExpression: string;
};

export type PositionSizingViewModel = {
  accountEquityLabel: string;
  approvedQuantityLabel: string;
  claudePresentLabel: string;
  claudeSizingOverrideAttemptedLabel: string;
  entryCostRequiredLabel: string;
  explanation: string | null;
  projectedMaxLossLabel: string;
  rejectionReasonsLabel: string;
  riskBudgetLabel: string;
  unitMaxLossLabel: string;
  warningsLabel: string;
};

export type ExecutionProposalViewModel = {
  legs: ExecutionProposalLegViewModel[];
  status: string | null;
};

export type ExecutionProposalLegViewModel = {
  quantity: string;
  side: string;
  symbol: string;
};

export function buildDecisionChainViewModel(
  records: DecisionChainRecord[],
): DecisionChainViewModel {
  const firstRow = records.find(
    (record) => record.row.target || record.row.theme || record.row.run_id,
  )?.row;
  const strategyRecord = records.find(
    (record) => record.recordType === "strategy_decision" && record.payload.ok,
  );
  const outcomeRecord = [...records]
    .reverse()
    .find(
      (record) =>
        (record.recordType === "trade_outcome" ||
          record.recordType === "outcome_correction") &&
        record.payload.ok,
    );

  const outcome =
    outcomeRecord?.payload.ok && isTradeOutcomeRecord(outcomeRecord)
      ? (outcomeRecord.payload.data as TradeOutcomePayload).outcome.outcome_type
      : "pending";
  const strategyStatus =
    strategyRecord?.payload.ok && strategyRecord.recordType === "strategy_decision"
      ? (strategyRecord.payload.data as StrategyDecisionPayload)
          .strategy_decision.status
      : firstRow?.strategy_status ?? "unknown";

  return {
    header: {
      executionMode: firstRow?.execution_mode ?? "unknown",
      outcome,
      runId: firstRow?.run_id ?? "unknown",
      strategyStatus,
      target: firstRow?.target ?? "Unknown target",
      theme: firstRow?.theme ?? "unknown",
    },
  };
}

export function buildStrategyEvidenceViewModel(
  payload: StrategyDecisionPayload,
): StrategyEvidenceViewModel {
  const candidate = payload.candidate_brief;

  return {
    contradictions: candidate?.contradictions ?? [],
    direction: candidate?.direction ?? "unknown",
    earningsDate: candidate?.earnings_date ?? "unknown",
    expression: candidate?.recommended_expression ?? "unknown",
    peerSignalScoreLabel: formatNumber(candidate?.peer_signal_score),
    peerScores:
      candidate?.peer_scores.map((peer) => ({
        missingFactorsLabel: formatList(peer.missing_factors),
        negativeFactorsLabel: formatList(peer.negative_factors),
        positiveFactorsLabel: formatList(peer.positive_factors),
        scoreLabel: formatNumber(peer.score),
        ticker: peer.ticker,
      })) ?? [],
    positivePeerRatioLabel: formatRatio(candidate?.positive_peer_ratio),
    reportedPeersLabel: formatList(candidate?.reported_peers ?? []),
    reportTime: candidate?.report_time ?? "unknown",
    status: payload.strategy_decision.status,
    supportingEvidence: candidate?.supporting_evidence ?? [],
    thesis: payload.thesis,
  };
}

export function buildAnalystReviewViewModel(
  payload: AnalystReviewPayload,
): AnalystReviewViewModel {
  const analysis = payload.analysis;

  return {
    analystConvictionLabel: formatNumber(analysis?.conviction_score),
    citedCitationIdsLabel: formatList(analysis?.cited_citation_ids ?? []),
    contradictionsLabel: formatList(analysis?.contradictions ?? []),
    missingContextLabel: formatList(analysis?.missing_context ?? []),
    reasoning: analysis?.reasoning ?? null,
    recommendation: analysis?.recommendation ?? payload.status,
    suggestedExpression: analysis?.suggested_expression ?? "unknown",
  };
}

export function buildPositionSizingViewModel(
  payload: PositionSizingPayload,
): PositionSizingViewModel {
  const sizing = payload.position_sizing_decision;

  return {
    accountEquityLabel: formatMoney(sizing.account_equity),
    approvedQuantityLabel: String(sizing.approved_quantity),
    claudePresentLabel: formatBoolean(sizing.claude_present),
    claudeSizingOverrideAttemptedLabel: formatBoolean(
      sizing.claude_sizing_override_attempted,
    ),
    entryCostRequiredLabel: formatMoney(sizing.entry_cost_required),
    explanation: sizing.explanation ?? null,
    projectedMaxLossLabel: formatMoney(sizing.projected_max_loss),
    rejectionReasonsLabel: formatList(sizing.rejection_reasons),
    riskBudgetLabel: formatMoney(sizing.risk_budget),
    unitMaxLossLabel: formatMoney(sizing.unit_max_loss),
    warningsLabel: formatList(sizing.warnings),
  };
}

export function buildExecutionProposalViewModel(
  payload: ExecutionProposalPayload,
): ExecutionProposalViewModel {
  return {
    legs: extractAvailableLegs(payload),
    status: stringField(payload, "proposal_status"),
  };
}

function extractAvailableLegs(
  payload: ExecutionProposalPayload,
): ExecutionProposalLegViewModel[] {
  const legs = payload.legs;
  if (!Array.isArray(legs)) {
    return [];
  }

  return legs.flatMap((leg) => {
    if (!isRecord(leg)) {
      return [];
    }

    const side = primitiveField(leg, "side");
    const symbol = primitiveField(leg, "symbol");
    const quantity = primitiveField(leg, "quantity");
    if (side == null && symbol == null && quantity == null) {
      return [];
    }

    return [
      {
        quantity: quantity ?? "-",
        side: side ?? "-",
        symbol: symbol ?? "-",
      },
    ];
  });
}

function stringField(
  payload: ExecutionProposalPayload,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function primitiveField(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  const value = payload[key];
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "unknown";
  }
  return String(value);
}

function formatRatio(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "unknown";
  }
  return `${Math.round(value * 100)}%`;
}

function formatBoolean(value: boolean): string {
  return value ? "Yes" : "No";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTradeOutcomeRecord(record: DecisionChainRecord): boolean {
  return (
    record.recordType === "trade_outcome" ||
    record.recordType === "outcome_correction"
  );
}
