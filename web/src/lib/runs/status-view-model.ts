import type { OperatorStatus } from "@/lib/operator/schemas";
import type {
  ProviderErrorRow,
  RunRow,
  StorageAuditRow,
} from "@/lib/runs/schemas";

export type OperationalStatus = "clear" | "attention" | "blocked";

export type RunsDailyHaltStatus = {
  status: "allowed" | "halted";
  createdAt: string | null;
};

export type RecentRunDisplayRow = RunRow & {
  decisionCountLabel: string;
};

export type StorageAuditDisplayRow = StorageAuditRow & {
  errorRateLabel: string;
};

export type RunsStatusViewModel = {
  operationalStatus: OperationalStatus;
  operationalLabel: string;
  operationalReasons: string[];
  latestRun: RunRow | null;
  recentRunRows: RecentRunDisplayRow[];
  storageAuditRows: StorageAuditDisplayRow[];
  providerErrorCount: number;
};

export function buildRunsStatusViewModel({
  dailyHalt,
  operatorStatus,
  providerErrors,
  runs,
  storageAudit,
}: {
  dailyHalt: RunsDailyHaltStatus;
  operatorStatus: OperatorStatus;
  providerErrors: ProviderErrorRow[];
  runs: RunRow[];
  storageAudit: StorageAuditRow[];
}): RunsStatusViewModel {
  const latestRun = runs[0] ?? null;
  const blockedReasons = blockedOperationalReasons(operatorStatus, dailyHalt);
  const attentionReasons = attentionOperationalReasons(
    latestRun,
    providerErrors,
    storageAudit,
  );
  const operationalStatus: OperationalStatus = blockedReasons.length
    ? "blocked"
    : attentionReasons.length
      ? "attention"
      : "clear";
  const operationalReasons =
    operationalStatus === "blocked"
      ? blockedReasons
      : operationalStatus === "attention"
        ? attentionReasons
        : ["No current operational blockers."];

  return {
    operationalStatus,
    operationalLabel: operationalLabel(operationalStatus),
    operationalReasons,
    latestRun,
    recentRunRows: runs.map(toRecentRunRow),
    storageAuditRows: storageAudit.map(toStorageAuditRow),
    providerErrorCount: providerErrors.length,
  };
}

export function formatStorageErrorRate(
  errorCount: number,
  attemptedCount: number,
): string {
  if (attemptedCount <= 0) {
    return "n/a";
  }
  return `${Math.round((errorCount / attemptedCount) * 100)}%`;
}

function blockedOperationalReasons(
  operatorStatus: OperatorStatus,
  dailyHalt: RunsDailyHaltStatus,
): string[] {
  const reasons: string[] = [];
  if (operatorStatus.killSwitch.status === "active") {
    reasons.push(
      operatorStatus.killSwitch.reason
        ? `Kill switch active: ${operatorStatus.killSwitch.reason}`
        : "Kill switch active",
    );
  }
  if (dailyHalt.status === "halted") {
    reasons.push(
      dailyHalt.createdAt
        ? `Daily halt active since ${dailyHalt.createdAt}`
        : "Daily halt active",
    );
  }
  return reasons;
}

function attentionOperationalReasons(
  latestRun: RunRow | null,
  providerErrors: ProviderErrorRow[],
  storageAudit: StorageAuditRow[],
): string[] {
  const reasons: string[] = [];
  if (!latestRun) {
    reasons.push("No recent runs recorded");
  } else if (isAttentionRunStatus(latestRun.status)) {
    reasons.push(`Latest run status is ${latestRun.status}`);
  }

  if (providerErrors.length > 0) {
    reasons.push(
      `${providerErrors.length} recent provider ${
        providerErrors.length === 1 ? "error" : "errors"
      }`,
    );
  }

  const storageRowsWithErrors = storageAudit.filter((row) => row.errorCount > 0);
  if (storageRowsWithErrors.length > 0) {
    reasons.push(
      `${storageRowsWithErrors.length} storage write audit ${
        storageRowsWithErrors.length === 1 ? "row" : "rows"
      } with errors`,
    );
  }

  return reasons;
}

function isAttentionRunStatus(status: string): boolean {
  const normalized = status.toLowerCase();
  return ["failed", "error", "halted", "blocked", "partial"].includes(normalized);
}

function toRecentRunRow(row: RunRow): RecentRunDisplayRow {
  return {
    ...row,
    decisionCountLabel: decisionCountLabel(row.payload),
  };
}

function toStorageAuditRow(row: StorageAuditRow): StorageAuditDisplayRow {
  return {
    ...row,
    errorRateLabel: formatStorageErrorRate(
      row.errorCount,
      row.attemptedRecordCount,
    ),
  };
}

function decisionCountLabel(payload: Record<string, unknown>): string {
  const totalDecisionCount = numberField(payload.total_decision_count);
  if (totalDecisionCount !== null) {
    return String(totalDecisionCount);
  }

  const recordCount = numberField(payload.record_count);
  if (recordCount !== null) {
    return String(recordCount);
  }

  return "unknown";
}

function numberField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function operationalLabel(status: OperationalStatus): string {
  if (status === "blocked") return "Blocked";
  if (status === "attention") return "Attention";
  return "Clear";
}
