/**
 * Command palette tests.
 *
 * Covers the keyboard contract (the reason the palette exists) and the honesty
 * requirement: the palette navigates, and says plainly that company-wide search
 * is not wired up rather than appearing to search and returning nothing.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import CommandPalette from "../CommandPalette";

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPalette(onClose = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/today"]}>
      <CommandPalette open onClose={onClose} />
      <LocationProbe />
      <Routes>
        <Route path="*" element={null} />
      </Routes>
    </MemoryRouter>,
  );
  return onClose;
}

describe("CommandPalette", () => {
  it("focuses its search field when opened", () => {
    renderPalette();
    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("lists navigation commands", () => {
    renderPalette();
    expect(
      screen.getByRole("option", { name: /Go to Today/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Go to Missions/ }),
    ).toBeInTheDocument();
  });

  it("filters as the user types", async () => {
    const user = userEvent.setup();
    renderPalette();
    await user.type(screen.getByRole("combobox"), "memor");
    expect(screen.getByRole("option", { name: /Go to Memory/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Go to Today/ })).toBeNull();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    renderPalette();
    await user.type(screen.getByRole("combobox"), "zzzzz");
    expect(screen.getByText(/no commands match/i)).toBeInTheDocument();
  });

  it("navigates and closes when a command is chosen with Enter", async () => {
    const user = userEvent.setup();
    const onClose = renderPalette();
    await user.type(screen.getByRole("combobox"), "missions");
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent("/missions");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("navigates when a command is clicked", async () => {
    const user = userEvent.setup();
    const onClose = renderPalette();
    await user.click(screen.getByRole("option", { name: /Go to Memory/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("/memory");
    expect(onClose).toHaveBeenCalled();
  });

  it("moves the active option with the arrow keys", async () => {
    const user = userEvent.setup();
    renderPalette();
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = renderPalette();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("states that company-wide search is not available yet", () => {
    renderPalette();
    expect(
      screen.getByText(/company-wide search arrives with the brain search service/i),
    ).toBeInTheDocument();
  });

  it("is exposed as a modal dialog with a name", () => {
    renderPalette();
    expect(
      screen.getByRole("dialog", { name: "Command palette" }),
    ).toBeInTheDocument();
  });
});
