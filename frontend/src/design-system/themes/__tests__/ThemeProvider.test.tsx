/**
 * Theme system tests.
 *
 * These cover the behaviours a user can observe: the preference applies to the
 * document, it persists across reloads, "system" follows the OS, and the
 * default is never a hardcoded light or dark.
 */

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ThemeProvider,
  THEME_STORAGE_KEY,
  readStoredTheme,
  resolveTheme,
} from "../ThemeProvider";
import ThemeToggle from "../../../components/layout/ThemeToggle";

/** Replace matchMedia so "system" can be driven from a test. */
function stubSystemTheme(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("dark") ? prefersDark : !prefersDark,
      media: query,
      addEventListener: (_: string, cb: () => void) => listeners.add(cb),
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
      addListener: (cb: () => void) => listeners.add(cb),
      removeListener: (cb: () => void) => listeners.delete(cb),
      dispatchEvent: () => false,
      onchange: null,
    })),
  );
  return listeners;
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("theme preference storage", () => {
  it("defaults to following the system, not to a fixed theme", () => {
    expect(readStoredTheme()).toBe("system");
  });

  it("ignores a tampered or unknown stored value", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon");
    expect(readStoredTheme()).toBe("system");
  });

  it("reads a valid stored preference", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(readStoredTheme()).toBe("dark");
  });
});

describe("resolveTheme", () => {
  it("passes explicit preferences through unchanged", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("resolves system against the OS setting", () => {
    stubSystemTheme(true);
    expect(resolveTheme("system")).toBe("dark");
    vi.unstubAllGlobals();
    stubSystemTheme(false);
    expect(resolveTheme("system")).toBe("light");
  });
});

describe("ThemeProvider", () => {
  it("applies the resolved theme to the document element", () => {
    stubSystemTheme(true);
    render(
      <ThemeProvider>
        <div />
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("persists a chosen preference", async () => {
    stubSystemTheme(false);
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );

    // system -> light -> dark
    await user.click(screen.getByRole("button"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    await user.click(screen.getByRole("button"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("announces the current and next theme for screen readers", () => {
    stubSystemTheme(false);
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    expect(screen.getByRole("button")).toHaveAccessibleName(
      /system theme.*switch to light theme/i,
    );
  });
});
