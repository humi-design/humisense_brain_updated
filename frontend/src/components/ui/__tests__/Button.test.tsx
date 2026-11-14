/**
 * UI primitive tests.
 *
 * Focused on the contracts other code depends on: variants render the right
 * class, icon-only buttons always have an accessible name, and loading state is
 * announced rather than only shown.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Button, IconButton } from "../Button";
import { Bell, Plus } from "../icons";

describe("Button", () => {
  it("defaults to the secondary variant at medium size", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("hs-btn-secondary");
    expect(button).not.toHaveClass("hs-btn-sm");
  });

  it("applies the requested variant and size", () => {
    render(
      <Button variant="primary" size="sm">
        Connect
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Connect" });
    expect(button).toHaveClass("hs-btn-primary");
    expect(button).toHaveClass("hs-btn-sm");
  });

  it("renders an icon with the label", () => {
    render(<Button icon={Plus}>Add</Button>);
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("does not fire onClick while loading", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button loading onClick={onClick}>
        Saving
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("renders as a link when given a destination", () => {
    render(
      <MemoryRouter>
        <Button to="/apps">Apps</Button>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Apps" })).toHaveAttribute(
      "href",
      "/apps",
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not fire onClick when disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button disabled onClick={onClick}>
        Nope
      </Button>,
    );
    await user.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("IconButton", () => {
  it("requires a label and exposes it as the accessible name", () => {
    render(<IconButton label="Notifications" icon={Bell} />);
    expect(
      screen.getByRole("button", { name: "Notifications" }),
    ).toBeInTheDocument();
  });

  it("is reachable and activatable by keyboard", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton label="Notifications" icon={Bell} onClick={onClick} />);
    await user.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
