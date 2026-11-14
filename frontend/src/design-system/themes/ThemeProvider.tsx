/**
 * Theme resolution and persistence.
 *
 * Three preferences are supported: `light`, `dark` and `system`. `system`
 * follows the operating system and keeps following it, so a user who changes
 * their OS theme while the app is open sees the app change too.
 *
 * The stored value is a UI preference only. Nothing about the user, their
 * organization or their role is ever written here — those come from the
 * server. See `src/auth/` for identity.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "humisense.theme";
export const DEFAULT_THEME: ThemePreference = "system";

/** Read the stored preference, tolerating unavailable storage. */
export function readStoredTheme(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* storage unavailable; fall through to the default */
  }
  return DEFAULT_THEME;
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Turn a preference into the theme that should actually be painted. */
export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return systemPrefersDark() ? "dark" : "light";
  return preference;
}

export function applyTheme(theme: ResolvedTheme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside <ThemeProvider>");
  return value;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    readStoredTheme(),
  );
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(readStoredTheme()),
  );

  // Keep the painted theme in step with the preference. The inline script in
  // index.html already did this before first paint; this keeps it correct for
  // every later change.
  useEffect(() => {
    const next = resolveTheme(preference);
    setResolved(next);
    applyTheme(next);
  }, [preference]);

  // When following the system, react to the OS changing underneath us.
  useEffect(() => {
    if (preference !== "system" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next: ResolvedTheme = query.matches ? "dark" : "light";
      setResolved(next);
      applyTheme(next);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage may be unavailable. The theme still applies for this session.
    }
  }, []);

  const value = useMemo(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
