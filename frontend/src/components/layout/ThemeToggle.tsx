/**
 * Theme switcher.
 *
 * Cycles light → dark → system. The accessible name states the *current* mode
 * and the button announces what it will switch to, so it is usable without
 * seeing the icon.
 */

import { useTheme, type ThemePreference } from "../../design-system/themes/ThemeProvider";
import { Monitor, Moon, Sun } from "../ui/icons";

const ORDER: ThemePreference[] = ["system", "light", "dark"];

const LABELS: Record<ThemePreference, string> = {
  system: "System theme",
  light: "Light theme",
  dark: "Dark theme",
};

export default function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  const next = ORDER[(ORDER.indexOf(preference) + 1) % ORDER.length];
  const Icon = preference === "dark" ? Moon : preference === "light" ? Sun : Monitor;

  return (
    <button
      type="button"
      className="hs-icon-btn"
      onClick={() => setPreference(next)}
      aria-label={`${LABELS[preference]}. Switch to ${LABELS[next].toLowerCase()}.`}
      title={`${LABELS[preference]} — switch to ${LABELS[next].toLowerCase()}`}
    >
      <Icon size={16} aria-hidden="true" />
    </button>
  );
}
