import { describe, expect, it } from "vitest";
import type { OperatorStatus } from "@/lib/operator/schemas";
import {
  buildRunsStatusViewModel,
  formatStorageErrorRate,
} from "@/lib/runs/status-view-model";
import type {
  ProviderErrorRow,
  RunRow,
  StorageAuditRow,
} from "@/lib/runs/schemas";

function operatorStatus(overrides: Partial<OperatorStatus> = {}): OperatorStatus {
  return {
    executionMode: "propose_only",
    modeSource: "default",
    killSwitch: {
      status: "inactive",
      reason: null,
      activatedAt: null,
      activatedBy: null,
      resetAt: null,
      resetBy: null,
      warnings: [],
    },
    latestModeAuthorization: null,
    warnings: [],
    ...overrides,
  };
}

function run(overrides: Partial<RunRow> = {}): RunRow {
  return {
    runId: "scheduled:2026-06-04",
    triggerType: "scheduled",
    scheduledDate: "2026-06-04",
    currentDate: "2026-06-04",
    windowStart: "2026-06-04",
    windowEnd: "2026-06-06",
    status: "completed",
    payload: { total_decision_count: 3 },
    schemaVersion: 1,
    createdAt: "2026-06-04T12:00:00Z",
    ...overrides,
  };
}

function providerError(
  overrides: Partial<ProviderErrorRow> = {},
): ProviderErrorRow {
  return {
    providerErrorId: "err-1",
    provider: "finnhub",
    errorType: "rate_limited",
    runId: "scheduled:2026-06-04",
    target: "NTNX",
    source: "earnings",
    message: "rate limit",
    payload: {},
    schemaVersion: 1,
    createdAt: "2026-06-04T12:05:00Z",
    ...overrides,
  };
}

function storageAudit(
  overrides: Partial<StorageAuditRow> = {},
): StorageAuditRow {
  return {
    storageWriteAuditId: "audit-1",
    provider: "supabase",
    tableName: "decision_records",
    runId: "scheduled:2026-06-04",
    attemptedRecordCount: 10,
    writtenRecordCount: 9,
    errorCount: 1,
    payload: {},
    schemaVersion: 1,
    createdAt: "2026-06-04T12:06:00Z",
    ...overrides,
  };
}

describe("runs status view model", () => {
  it("returns blocked when safety controls stop the system", () => {
    const view = buildRunsStatusViewModel({
      runs: [run()],
      providerErrors: [],
      storageAudit: [],
      dailyHalt: { status: "halted", createdAt: "2026-06-04T12:00:00Z" },
      operatorStatus: operatorStatus({
        killSwitch: {
          status: "active",
          reason: "manual stop",
          activatedAt: null,
          activatedBy: null,
          resetAt: null,
          resetBy: null,
          warnings: [],
        },
      }),
    });

    expect(view.operationalStatus).toBe("blocked");
    expect(view.operationalLabel).toBe("Blocked");
    expect(view.operationalReasons).toEqual([
      "Kill switch active: manual stop",
      "Daily halt active since 2026-06-04T12:00:00Z",
    ]);
  });

  it("returns attention for provider, storage, latest-run, or missing-run symptoms", () => {
    const view = buildRunsStatusViewModel({
      runs: [run({ status: "failed" })],
      providerErrors: [providerError()],
      storageAudit: [storageAudit()],
      dailyHalt: { status: "allowed", createdAt: null },
      operatorStatus: operatorStatus(),
    });

    expect(view.operationalStatus).toBe("attention");
    expect(view.operationalLabel).toBe("Attention");
    expect(view.operationalReasons).toEqual([
      "Latest run status is failed",
      "1 recent provider error",
      "1 storage write audit row with errors",
    ]);

    const noRunView = buildRunsStatusViewModel({
      runs: [],
      providerErrors: [],
      storageAudit: [],
      dailyHalt: { status: "allowed", createdAt: null },
      operatorStatus: operatorStatus(),
    });

    expect(noRunView.operationalStatus).toBe("attention");
    expect(noRunView.operationalReasons).toEqual(["No recent runs recorded"]);
  });

  it("returns clear when all current status sources are clean", () => {
    const view = buildRunsStatusViewModel({
      runs: [run()],
      providerErrors: [],
      storageAudit: [storageAudit({ errorCount: 0, writtenRecordCount: 10 })],
      dailyHalt: { status: "allowed", createdAt: null },
      operatorStatus: operatorStatus(),
    });

    expect(view.operationalStatus).toBe("clear");
    expect(view.operationalLabel).toBe("Clear");
    expect(view.operationalReasons).toEqual(["No current operational blockers."]);
  });

  it("derives decision counts and storage error-rate labels", () => {
    const view = buildRunsStatusViewModel({
      runs: [
        run({ runId: "run-total", payload: { total_decision_count: 7 } }),
        run({ runId: "run-records", payload: { record_count: 4 } }),
        run({ runId: "run-empty", payload: {} }),
      ],
      providerErrors: [],
      storageAudit: [
        storageAudit({ attemptedRecordCount: 10, errorCount: 1 }),
        storageAudit({
          storageWriteAuditId: "audit-zero",
          attemptedRecordCount: 0,
          writtenRecordCount: 0,
          errorCount: 0,
        }),
      ],
      dailyHalt: { status: "allowed", createdAt: null },
      operatorStatus: operatorStatus(),
    });

    expect(view.recentRunRows.map((row) => row.decisionCountLabel)).toEqual([
      "7",
      "4",
      "unknown",
    ]);
    expect(view.storageAuditRows.map((row) => row.errorRateLabel)).toEqual([
      "10%",
      "n/a",
    ]);
    expect(formatStorageErrorRate(2, 8)).toBe("25%");
  });
});
