/**
 * System state tests.
 *
 * The important property here is *honesty*: an empty state and an error state
 * must be distinguishable, and the "not available yet" state must not be
 * mistakable for either real data or a failure.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  LoadingState,
  NotAvailableState,
  OfflineState,
  UnauthorizedState,
} from "../States";

describe("state semantics", () => {
  it("tells the user when there is genuinely no data", () => {
    render(<EmptyState title="Nothing here yet" />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("distinguishes a failed request from empty data", () => {
    const { unmount } = render(<EmptyState title="No connections" />);
    expect(screen.queryByText(/could not/i)).not.toBeInTheDocument();
    unmount();

    render(<ErrorState title="Could not load connections" />);
    expect(screen.getByText("Could not load connections")).toBeInTheDocument();
    // The error state is visually distinct, not just differently worded.
    expect(document.querySelector(".hs-state-danger")).not.toBeNull();
  });

  it("marks planned functionality as not available rather than empty", () => {
    render(
      <NotAvailableState
        title="Awaiting the Work Intelligence layer"
        description="Provided by Layer 2."
      />,
    );
    expect(
      screen.getByText("Awaiting the Work Intelligence layer"),
    ).toBeInTheDocument();
    expect(screen.getByText("Provided by Layer 2.")).toBeInTheDocument();
  });

  it("announces loading to assistive technology", () => {
    render(<LoadingState label="Loading connections" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Loading connections")).toBeInTheDocument();
  });

  it("offers a retry action on error", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <ErrorState
        title="Could not load"
        action={{ label: "Retry", onClick: onRetry }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("has a distinct presentation for offline, expired session and denied access", () => {
    const { unmount: u1 } = render(<OfflineState />);
    expect(document.querySelector(".hs-state-warning")).not.toBeNull();
    u1();

    const { unmount: u2 } = render(<UnauthorizedState />);
    expect(document.querySelector(".hs-state-warning")).not.toBeNull();
    u2();

    render(<ForbiddenState />);
    expect(document.querySelector(".hs-state-danger")).not.toBeNull();
  });

  it("shows the failure reason when one is supplied", () => {
    render(
      <ErrorState
        title="Could not load"
        description="Connection to the server timed out."
      />,
    );
    expect(
      screen.getByText("Connection to the server timed out."),
    ).toBeInTheDocument();
  });
});
