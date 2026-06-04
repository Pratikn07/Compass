import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RunSwitcher } from "@/features/decisions/run-switcher";
import type { RunRow } from "@/features/decisions/decision-list.types";

function run(overrides: Partial<RunRow> = {}): RunRow {
  return {
    run_id: "scheduled:2026-06-02",
    trigger_type: "scheduled",
    scheduled_date: "2026-06-02",
    current_date: "2026-06-02",
    window_start: "2026-06-02",
    window_end: "2026-06-04",
    status: "completed",
    payload: {},
    schema_version: 1,
    created_at: "2026-06-02T12:00:00Z",
    ...overrides,
  } as RunRow;
}

const runs = [
  run({ run_id: "scheduled:2026-06-03", created_at: "2026-06-03T12:00:00Z" }),
  run({ run_id: "scheduled:2026-06-02", created_at: "2026-06-02T12:00:00Z" }),
  run({ run_id: "scheduled:2026-06-01", created_at: "2026-06-01T12:00:00Z" }),
];

describe("RunSwitcher", () => {
  it("selects the newer run when older-newer navigation is used", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <RunSwitcher runs={runs} selectedRunId="scheduled:2026-06-02" onSelect={onSelect} />,
    );

    await user.click(screen.getByRole("button", { name: /newer run/i }));
    expect(onSelect).toHaveBeenCalledWith("scheduled:2026-06-03");
  });

  it("selects the older run when older navigation is used", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <RunSwitcher runs={runs} selectedRunId="scheduled:2026-06-02" onSelect={onSelect} />,
    );

    await user.click(screen.getByRole("button", { name: /older run/i }));
    expect(onSelect).toHaveBeenCalledWith("scheduled:2026-06-01");
  });

  it("disables newer navigation on the most recent run", () => {
    render(
      <RunSwitcher runs={runs} selectedRunId="scheduled:2026-06-03" onSelect={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: /newer run/i })).toBeDisabled();
  });

  it("selects a run from the dropdown", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <RunSwitcher runs={runs} selectedRunId="scheduled:2026-06-02" onSelect={onSelect} />,
    );

    await user.selectOptions(
      screen.getByLabelText("Select run"),
      "scheduled:2026-06-01",
    );
    expect(onSelect).toHaveBeenCalledWith("scheduled:2026-06-01");
  });
});
