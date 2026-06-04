import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

import { GET as getStatus } from "@/app/api/operator/status/route";
import { POST as postModeAuthorization } from "@/app/api/operator/mode-authorization/route";
import { createClient } from "@/lib/supabase/server";

const mockedCreateClient = vi.mocked(createClient);

function mockUser(email = "operator@example.com") {
  mockedCreateClient.mockResolvedValue({
    auth: {
      getUser: vi.fn().mockResolvedValue({
        data: { user: { id: "user-1", email } },
        error: null,
      }),
    },
  } as never);
}

describe("operator proxy routes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockedCreateClient.mockReset();
    process.env.PRESCIENT_OPERATOR_API_URL = "http://operator.test";
    process.env.PRESCIENT_OPERATOR_API_TOKEN = "server-token";
  });

  it("GET /api/operator/status requires an authenticated Supabase user", async () => {
    mockedCreateClient.mockResolvedValue({
      auth: {
        getUser: vi.fn().mockResolvedValue({
          data: { user: null },
          error: null,
        }),
      },
    } as never);

    const response = await getStatus();

    expect(response.status).toBe(401);
  });

  it("GET /api/operator/status forwards with the server-only token", async () => {
    mockUser();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(Response.json({ execution_mode: "propose_only" }));

    const response = await getStatus();

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith("http://operator.test/status", {
      headers: { Authorization: "Bearer server-token" },
      cache: "no-store",
    });
  });

  it("POST /api/operator/mode-authorization rejects a live request with 403 and never forwards", async () => {
    mockUser("operator@example.com");
    const fetchMock = vi.spyOn(globalThis, "fetch");

    const request = new Request("http://localhost/api/operator/mode-authorization", {
      method: "POST",
      body: JSON.stringify({
        requested_mode: "live",
        reason: "attempting live",
      }),
    });

    const response = await postModeAuthorization(request);

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POST /api/operator/mode-authorization forwards actor from the session", async () => {
    mockUser("operator@example.com");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(Response.json({ status: "accepted", active_mode: "paper" }));

    const request = new Request("http://localhost/api/operator/mode-authorization", {
      method: "POST",
      body: JSON.stringify({
        requested_mode: "paper",
        reason: "paper validation",
      }),
    });

    const response = await postModeAuthorization(request);

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://operator.test/mode-authorization",
      expect.objectContaining({
        method: "POST",
        headers: {
          Authorization: "Bearer server-token",
          "Content-Type": "application/json",
        },
        cache: "no-store",
      }),
    );
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.actor).toBe("operator@example.com");
    expect(body.requested_mode).toBe("paper");
  });
});
