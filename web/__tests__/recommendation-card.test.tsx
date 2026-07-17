import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecommendationCard } from "@/components/recommendation-card";
import type { Recommendation } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...mod,
    api: { ...mod.api, acknowledge: vi.fn().mockResolvedValue({}) },
  };
});

import { api } from "@/lib/api";

const REC: Recommendation = {
  decision_id: "decision-7",
  decision_date: "2026-07-01",
  hypothesis: "h2",
  instrument: "ai-chips",
  theme_slug: "ai-chips",
  action: "consider_enter",
  reasoning: {
    tercile: "top",
    rank: 1,
    of: 10,
    etf: "SMH",
    claim: "edge is magnitude, not consistency",
    dev_top_beats_bottom: "20/41 quarters (48.8%)",
    validation_top_beats_bottom: "14/23 quarters (60.9%)",
  },
  base_rate: 34 / 64,
  attention_status: "normal",
  attention_reasons: [],
  acknowledged_at: null,
  acted_at: null,
  action_note: null,
};

describe("RecommendationCard", () => {
  it("always shows the base rate and the honesty line", () => {
    render(<RecommendationCard rec={REC} />);
    expect(screen.getByText(/Base rate 53\.1%/)).toBeInTheDocument();
    expect(screen.getByText(/20\/41 quarters/)).toBeInTheDocument();
    expect(screen.getByText(/14\/23 quarters/)).toBeInTheDocument();
    expect(
      screen.getByText(/magnitude, not per-quarter consistency/),
    ).toBeInTheDocument();
  });

  it("renders the instrument, rank, and ETF route", () => {
    render(<RecommendationCard rec={REC} />);
    expect(screen.getByText("ai-chips")).toBeInTheDocument();
    expect(screen.getByText(/via SMH/)).toBeInTheDocument();
    expect(screen.getByText(/Consider entering/)).toBeInTheDocument();
  });

  it("acknowledge fires the API and flips to seen", async () => {
    render(<RecommendationCard rec={REC} />);
    fireEvent.click(screen.getByRole("button", { name: /acknowledge/i }));
    await waitFor(() => expect(api.acknowledge).toHaveBeenCalledWith("decision-7"));
    expect(screen.getByText("Seen")).toBeInTheDocument();
  });
});
