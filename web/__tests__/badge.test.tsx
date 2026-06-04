import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "@/components/ui/badge";

describe("Badge", () => {
  it("renders danger styling for blocked risk decisions", () => {
    render(<Badge variant="danger">risk_blocked</Badge>);

    expect(screen.getByText("risk_blocked").className).toContain("danger");
  });

  it("renders success styling for proposed decisions", () => {
    render(<Badge variant="success">proposed</Badge>);

    expect(screen.getByText("proposed").className).toContain("success");
  });
});
