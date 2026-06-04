import type { BadgeVariant } from "./decision-list.types";
import type { DecisionChainRecordType } from "./decision-chain.types";

export const CHAIN_STEP: Record<
  DecisionChainRecordType,
  { label: string; order: number }
> = {
  strategy_decision: { label: "Strategy decision", order: 10 },
  analyst_review: { label: "Analyst review", order: 20 },
  risk_decision: { label: "Risk decision", order: 30 },
  position_sizing: { label: "Position sizing", order: 40 },
  execution_proposal: { label: "Execution proposal", order: 50 },
  trade_outcome: { label: "Outcome", order: 60 },
  outcome_correction: { label: "Outcome correction", order: 61 },
};

export function isDecisionChainRecordType(
  value: string,
): value is DecisionChainRecordType {
  return value in CHAIN_STEP;
}

export function badgeVariantForChainStatus(
  value: string | null | undefined,
): BadgeVariant {
  if (!value) return "muted";
  const normalized = value.toLowerCase();
  if (
    [
      "approved",
      "analyzed",
      "candidate_ready_for_analyst",
      "closed_win",
      "filled",
      "proposed",
      "risk_passed",
      "sized",
    ].includes(normalized)
  ) {
    return "success";
  }
  if (
    [
      "blocked",
      "broker_rejected",
      "closed_loss",
      "failed",
      "malformed",
      "rejected",
      "risk_blocked",
    ].includes(normalized)
  ) {
    return "danger";
  }
  if (["needs_more_context", "not_evaluable", "pending"].includes(normalized)) {
    return "warning";
  }
  return "muted";
}

export function formatChainValue(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replaceAll("_", " ");
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null) return "-";
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value);
}

export function formatList(values: string[]): string {
  return values.length ? values.join(", ") : "-";
}
