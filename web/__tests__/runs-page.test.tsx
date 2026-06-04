import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/runs/hooks", () => ({
  useDailyHaltStatus: () => ({
    isError: false,
    isLoading: false,
    data: { status: "allowed", record: null, createdAt: null },
  }),
  useLatestRuns: () => ({
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
        payload: {},
        schemaVersion: 1,
        createdAt: "2026-06-04T12:00:00Z",
      },
    ],
  }),
  useRecentProviderErrors: () => ({
    isError: false,
    isLoading: false,
    data: [],
  }),
  useRecentStorageAudit: () => ({
    isError: false,
    isLoading: false,
    data: [],
  }),
}));

const mutate = vi.fn();

vi.mock("@/lib/operator/hooks", () => ({
  useModeAuthorizationMutation: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate,
  }),
  useOperatorStatus: () => ({
    isError: false,
    isLoading: false,
    data: {
      executionMode: "propose_only",
      modeSource: "default",
      killSwitch: { status: "inactive", reason: null, warnings: [] },
      latestModeAuthorization: null,
      warnings: [],
    },
  }),
}));

import RunsPage from "@/app/(app)/runs/page";

describe("/runs page", () => {
  it("renders system status without trade execution actions", () => {
    render(<RunsPage />);

    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByText("scheduled:2026-06-04")).toBeInTheDocument();
    expect(screen.getByText("propose_only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sell/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /live/i })).not.toBeInTheDocument();
  });

  it("submits a guarded paper-mode request with a reason", async () => {
    const user = userEvent.setup();
    render(<RunsPage />);

    await user.type(screen.getByLabelText("Reason"), "paper validation");
    await user.click(screen.getByRole("button", { name: /request paper mode/i }));

    expect(mutate).toHaveBeenCalledWith({
      requestedMode: "paper",
      reason: "paper validation",
    });
  });
});
