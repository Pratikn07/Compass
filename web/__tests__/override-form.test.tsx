import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverrideForm } from "@/components/override-form";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...mod,
    api: { ...mod.api, createOverride: vi.fn().mockResolvedValue({}) },
  };
});

import { api } from "@/lib/api";

describe("OverrideForm", () => {
  it("blocks a blank reason with a visible error", async () => {
    const onCreated = vi.fn();
    render(<OverrideForm onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/what you did/i), {
      target: { value: "sold SMH" },
    });
    fireEvent.change(screen.getByLabelText(/why/i), { target: { value: "  " } });
    fireEvent.submit(screen.getByTestId("override-form"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/reason is required/i);
    expect(api.createOverride).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("submits trimmed what/reason and notifies parent", async () => {
    const onCreated = vi.fn();
    render(<OverrideForm onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/what you did/i), {
      target: { value: " sold SMH " },
    });
    fireEvent.change(screen.getByLabelText(/why/i), {
      target: { value: " panicked on a red day " },
    });
    fireEvent.submit(screen.getByTestId("override-form"));
    await waitFor(() =>
      expect(api.createOverride).toHaveBeenCalledWith(
        "sold SMH",
        "panicked on a red day",
      ),
    );
    expect(onCreated).toHaveBeenCalled();
  });
});
