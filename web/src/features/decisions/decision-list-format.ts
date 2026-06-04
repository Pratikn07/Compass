import type { BadgeVariant } from "./decision-list.types";

const SUCCESS_VALUES = new Set([
  "approved",
  "candidate_ready_for_analyst",
  "proposed",
]);

const DANGER_VALUES = new Set([
  "blocked",
  "broker_rejected",
  "malformed",
  "rejected",
  "rejected_with_reason",
  "risk_blocked",
]);

const MUTED_VALUES = new Set(["no_trade", "pending", "propose_only"]);

export function badgeVariantForDecisionValue(
  value: string | null | undefined,
): BadgeVariant {
  if (!value) return "warning";
  const normalized = value.toLowerCase();
  if (SUCCESS_VALUES.has(normalized)) return "success";
  if (DANGER_VALUES.has(normalized)) return "danger";
  if (MUTED_VALUES.has(normalized)) return "muted";
  return "warning";
}

export function formatDecisionValue(value: string | null | undefined): string {
  if (!value) return "unknown";
  return value.replaceAll("_", " ");
}
