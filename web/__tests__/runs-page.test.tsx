import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockState = vi.hoisted(() => ({
  dailyHalt: {
    isError: false,
    isLoading: false,
    data: { status: "allowed", record: null, createdAt: null },
  },
  latestRuns: {
    isError: false,
    isLoading: false,
    data: [
      {
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
      },
    ],
  },
  providerErrors: {
    isError: false,
    isLoading: false,
    data: [
      {
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
      },
    ],
  },
  storageAudit: {
    isError: false,
    isLoading: false,
    data: [
      {
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
      },
    ],
  },
  operatorStatus: {
    isError: false,
    isLoading: false,
    data: {
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
    },
  },
  mutation: {
    data: undefined as unknown,
    error: null,
    isError: false,
    isPending: false,
    mutate: vi.fn(),
  },
}));

vi.mock("@/lib/runs/hooks", () => ({
  useDailyHaltStatus: () => mockState.dailyHalt,
  useLatestRuns: () => mockState.latestRuns,
  useRecentProviderErrors: () => mockState.providerErrors,
  useRecentStorageAudit: () => mockState.storageAudit,
}));

vi.mock("@/lib/operator/hooks", () => ({
  useModeAuthorizationMutation: () => mockState.mutation,
  useOperatorStatus: () => mockState.operatorStatus,
}));

import RunsPage from "@/app/(app)/runs/page";

describe("/runs page", () => {
  beforeEach(() => {
    mockState.dailyHalt = {
      isError: false,
      isLoading: false,
      data: { status: "allowed", record: null, createdAt: null },
    };
    mockState.latestRuns = {
      isError: false,
      isLoading: false,
      data: [
        {
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
        },
      ],
    };
    mockState.providerErrors = {
      isError: false,
      isLoading: false,
      data: [
        {
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
        },
      ],
    };
    mockState.storageAudit = {
      isError: false,
      isLoading: false,
      data: [
        {
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
        },
      ],
    };
    mockState.operatorStatus = {
      isError: false,
      isLoading: false,
      data: {
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
      },
    };
    mockState.mutation = {
      data: undefined as unknown,
      error: null,
      isError: false,
      isPending: false,
      mutate: vi.fn(),
    };
  });

  it("renders operational status and run health tables without trade execution actions", () => {
    render(<RunsPage />);

    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByText("Operational status")).toBeInTheDocument();
    expect(screen.getByText("Attention")).toBeInTheDocument();
    expect(screen.getByText("Recent runs")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Decision records" })).toBeInTheDocument();
    expect(screen.getAllByText("scheduled:2026-06-04").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("rate_limited")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Error rate" })).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
    expect(screen.getByText("propose_only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sell/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /live/i })).not.toBeInTheDocument();
  });

  it("renders a clear operational status when current sources are clean", () => {
    mockState.providerErrors = {
      isError: false,
      isLoading: false,
      data: [],
    };
    mockState.storageAudit = {
      isError: false,
      isLoading: false,
      data: [
        {
          storageWriteAuditId: "audit-1",
          provider: "supabase",
          tableName: "decision_records",
          runId: "scheduled:2026-06-04",
          attemptedRecordCount: 10,
          writtenRecordCount: 10,
          errorCount: 0,
          payload: {},
          schemaVersion: 1,
          createdAt: "2026-06-04T12:06:00Z",
        },
      ],
    };

    render(<RunsPage />);

    expect(screen.getByText("Clear")).toBeInTheDocument();
    expect(screen.getByText("No current operational blockers.")).toBeInTheDocument();
  });

  it("requires a 10 character reason before submitting mode authorization", async () => {
    const user = userEvent.setup();
    render(<RunsPage />);

    const reason = screen.getByLabelText("Reason");
    const button = screen.getByRole("button", { name: /request paper mode/i });

    expect(reason.tagName).toBe("TEXTAREA");
    expect(screen.getByText("0/1000")).toBeInTheDocument();
    expect(button).toBeDisabled();

    await user.type(reason, "short");

    expect(screen.getByText("5/1000")).toBeInTheDocument();
    expect(button).toBeDisabled();

    await user.clear(reason);
    await user.type(reason, "paper mode validation");
    await user.click(button);

    expect(mockState.mutation.mutate).toHaveBeenCalledWith({
      requestedMode: "paper",
      reason: "paper mode validation",
    });
  });

  it("shows a dedicated request status box", () => {
    render(<RunsPage />);

    expect(screen.getByText("Request status")).toBeInTheDocument();
    expect(screen.getByText("No request submitted in this session.")).toBeInTheDocument();

    mockState.mutation.data = {
      status: "accepted",
      requestedMode: "paper",
      previousMode: "propose_only",
      activeMode: "paper",
      actor: "operator@example.com",
      reason: "paper mode validation",
      createdAt: "2026-06-04T12:10:00Z",
      rejectionReasons: [],
      warnings: [],
    };

    render(<RunsPage />);

    expect(screen.getByText("Request accepted")).toBeInTheDocument();
    expect(screen.getByText("Active mode: paper")).toBeInTheDocument();
  });
});
