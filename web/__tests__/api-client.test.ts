import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

describe("Compass API client", () => {
  it("uses the same-origin server proxy and sends no browser API key", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.decisions();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/compass/v1/decisions?limit=50",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("acknowledges the stable decision id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await api.acknowledge("decision-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/compass/v1/recommendations/decision-1/ack",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
