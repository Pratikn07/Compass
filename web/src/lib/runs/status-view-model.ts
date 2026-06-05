import type { OperatorStatus } from "@/lib/operator/schemas";
import type {
  ProviderErrorRow,
  RunRow,
  StorageAuditRow,
  SystemHealthRow,
} from "@/lib/runs/schemas";

export type OperationalStatus = "clear" | "attention" | "blocked";
export type ProviderHealthStatus = "healthy" | "degraded" | "blocked" | "unknown";

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

export type ProviderHealthDisplayRow = {
  provider: string;
  status: ProviderHealthStatus;
  requests: number;
  cacheHits: number;
  cacheMisses: number;
  retries: number;
  errors: number;
  budgetLabel: string;
  lastSuccessAt: string | null;
  warnings: string[];
};

export type RunsStatusViewModel = {
  operationalStatus: OperationalStatus;
  operationalLabel: string;
  operationalReasons: string[];
  latestRun: RunRow | null;
  recentRunRows: RecentRunDisplayRow[];
  storageAuditRows: StorageAuditDisplayRow[];
  providerHealthRows: ProviderHealthDisplayRow[];
  providerErrorCount: number;
};

export function buildRunsStatusViewModel({
  dailyHalt,
  operatorStatus,
  providerErrors,
  runs,
  storageAudit,
  systemHealth,
}: {
  dailyHalt: RunsDailyHaltStatus;
  operatorStatus: OperatorStatus;
  providerErrors: ProviderErrorRow[];
  runs: RunRow[];
  storageAudit: StorageAuditRow[];
  systemHealth: SystemHealthRow[];
}): RunsStatusViewModel {
  const latestRun = runs[0] ?? null;
  const latestProviderHealth = latestProviderHealthRecord(systemHealth);
  const blockedReasons = blockedOperationalReasons(operatorStatus, dailyHalt);
  const attentionReasons = attentionOperationalReasons(
    latestRun,
    providerErrors,
    storageAudit,
    latestProviderHealth,
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
    providerHealthRows: providerHealthRows(latestProviderHealth),
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
  latestProviderHealth: SystemHealthRow | null,
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

  if (
    latestProviderHealth &&
    latestProviderHealth.status !== "healthy" &&
    latestProviderHealth.status !== "unknown"
  ) {
    const detail = latestProviderHealth.detail
      ? `: ${latestProviderHealth.detail}`
      : "";
    reasons.push(
      `Provider health is ${latestProviderHealth.status}${detail}`,
    );
  } else if (latestProviderHealth?.status === "unknown") {
    const detail = latestProviderHealth.detail
      ? `: ${latestProviderHealth.detail}`
      : "";
    reasons.push(`Provider health is unknown${detail}`);
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

function latestProviderHealthRecord(rows: SystemHealthRow[]): SystemHealthRow | null {
  return rows.find((row) => row.component === "provider_health") ?? null;
}

function providerHealthRows(
  latestProviderHealth: SystemHealthRow | null,
): ProviderHealthDisplayRow[] {
  if (!latestProviderHealth) {
    return [];
  }

  const providers = latestProviderHealth.payload.providers;
  return Object.entries(providers)
    .map(([provider, payload]) => {
      const requests = numberField(payload.requests) ?? 0;
      const cacheHits = numberField(payload.cache_hits) ?? 0;
      const cacheMisses = numberField(payload.cache_misses) ?? 0;
      const retries = numberField(payload.retries) ?? 0;
      const errors = numberField(payload.errors) ?? 0;
      const budgetUsed = numberField(payload.budget_used);
      const budgetLimit = numberField(payload.budget_limit);
      const warnings = Array.isArray(payload.warnings)
        ? payload.warnings.filter((warning): warning is string => typeof warning === "string")
        : [];

      return {
        provider,
        status: providerHealthStatus({
          requests,
          cacheHits,
          errors,
          warnings,
          lastSuccessAt: stringField(payload.last_success_at),
        }),
        requests,
        cacheHits,
        cacheMisses,
        retries,
        errors,
        budgetLabel:
          budgetUsed === null || budgetLimit === null
            ? "n/a"
            : `${budgetUsed} / ${budgetLimit}`,
        lastSuccessAt: stringField(payload.last_success_at),
        warnings,
      };
    })
    .sort((left, right) => left.provider.localeCompare(right.provider));
}

function providerHealthStatus({
  requests,
  cacheHits,
  errors,
  warnings,
  lastSuccessAt,
}: {
  requests: number;
  cacheHits: number;
  errors: number;
  warnings: string[];
  lastSuccessAt: string | null;
}): ProviderHealthStatus {
  if (errors > 0 && requests === 0 && cacheHits === 0) {
    return "blocked";
  }
  if (errors > 0 || warnings.length > 0) {
    return "degraded";
  }
  if (requests > 0 || cacheHits > 0 || lastSuccessAt) {
    return "healthy";
  }
  return "unknown";
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

function stringField(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function operationalLabel(status: OperationalStatus): string {
  if (status === "blocked") return "Blocked";
  if (status === "attention") return "Attention";
  return "Clear";
}
