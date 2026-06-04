import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const routerPush = vi.fn();
const routerRefresh = vi.fn();
const locationAssign = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      signInWithPassword,
    },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    refresh: routerRefresh,
  }),
}));

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  beforeEach(() => {
    signInWithPassword.mockReset();
    routerPush.mockReset();
    routerRefresh.mockReset();
    locationAssign.mockReset();
    vi.stubGlobal("location", { assign: locationAssign });
  });

  it("uses browser navigation after successful Supabase sign-in", async () => {
    signInWithPassword.mockResolvedValue({ error: null });
    const user = userEvent.setup();

    render(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), "operator@example.com");
    await user.type(screen.getByLabelText("Password"), "prescient-local");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(locationAssign).toHaveBeenCalledWith("/decisions");
    });
    expect(routerPush).not.toHaveBeenCalled();
  });
});
