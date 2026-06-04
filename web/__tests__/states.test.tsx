import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";

describe("state components", () => {
  it("LoadingState announces a default loading state", () => {
    render(<LoadingState />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("EmptyState shows the provided message", () => {
    render(<EmptyState message="No decisions yet" />);

    expect(screen.getByText("No decisions yet")).toBeInTheDocument();
  });

  it("ErrorState surfaces the title and raw detail", () => {
    render(
      <ErrorState
        title="Decision payload did not match expected shape"
        detail={'{"bad":"blob"}'}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Decision payload did not match expected shape",
    );
    expect(screen.getByText(/"bad":"blob"/)).toBeInTheDocument();
  });
});
