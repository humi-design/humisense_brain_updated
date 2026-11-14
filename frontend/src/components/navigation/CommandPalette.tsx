/**
 * Global command palette (Cmd/Ctrl + K).
 *
 * This milestone implements *navigation* commands and a search entry point.
 * There is deliberately no company-wide search here: the backend has no search
 * endpoint, so the search input states that plainly rather than returning
 * fabricated results.
 *
 * Accessibility: focus is trapped while open, Escape closes, and the shortcut
 * is ignored while the user is typing in a field so it never swallows input.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { ALL_NAV_ITEMS } from "./navConfig";
import { Command, CornerDownLeft, Search } from "../ui/icons";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

/** True when the event target is somewhere the user is typing. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const commands = useMemo(
    () =>
      ALL_NAV_ITEMS.map((item) => ({
        id: item.to,
        label: `Go to ${item.label}`,
        hint: item.description,
        keywords: `${item.label} ${item.description}`.toLowerCase(),
        run: () => {
          navigate(item.to);
          onClose();
        },
      })),
    [navigate, onClose],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((c) => c.keywords.includes(needle));
  }, [commands, query]);

  // Reset transient state each time the palette opens, and move focus into it.
  // useLayoutEffect focuses before the browser paints, so the field is ready the
  // moment the palette appears rather than a frame later.
  useLayoutEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((i) => (filtered.length ? (i + 1) % filtered.length : 0));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((i) =>
          filtered.length ? (i - 1 + filtered.length) % filtered.length : 0,
        );
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const chosen = filtered[activeIndex];
        if (chosen) chosen.run();
        return;
      }
      // Trap Tab inside the dialog.
      if (event.key === "Tab") {
        const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    },
    [activeIndex, filtered, onClose],
  );

  if (!open) return null;

  return (
    <div
      className="hs-overlay"
      onMouseDown={(event) => {
        // Close only when the click starts on the backdrop itself.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="hs-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={handleKeyDown}
      >
        <div className="hs-palette-search">
          <Search size={15} aria-hidden="true" />
          <input
            ref={inputRef}
            className="hs-palette-input"
            placeholder="Search commands and pages…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search commands"
            aria-controls="hs-palette-list"
            aria-activedescendant={
              filtered[activeIndex] ? `hs-cmd-${activeIndex}` : undefined
            }
            role="combobox"
            aria-expanded="true"
          />
          <kbd className="hs-kbd">Esc</kbd>
        </div>

        <div className="hs-palette-list" id="hs-palette-list" role="listbox">
          {filtered.length === 0 ? (
            <div className="hs-palette-empty">
              No commands match “{query}”.
            </div>
          ) : (
            filtered.map((command, index) => (
              <button
                key={command.id}
                id={`hs-cmd-${index}`}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className={`hs-palette-item${index === activeIndex ? " is-active" : ""}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={command.run}
              >
                <Command size={14} aria-hidden="true" />
                <span className="hs-palette-label">{command.label}</span>
                <span className="hs-palette-hint">{command.hint}</span>
                {index === activeIndex && (
                  <CornerDownLeft size={13} aria-hidden="true" />
                )}
              </button>
            ))
          )}
        </div>

        <div className="hs-palette-foot">
          <span className="hs-palette-note">
            Company-wide search arrives with the Brain search service. Navigation
            commands work now.
          </span>
          <span className="hs-row" style={{ gap: 6 }}>
            <kbd className="hs-kbd">↑↓</kbd>
            <kbd className="hs-kbd">↵</kbd>
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Registers the Cmd/Ctrl+K shortcut.
 *
 * Kept as a hook so the shell stays readable. The handler is a no-op while the
 * user is typing, so the shortcut never steals a keystroke from an input.
 */
export function useCommandPaletteShortcut(toggle: () => void): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isPaletteKey =
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (!isPaletteKey) return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);
}
