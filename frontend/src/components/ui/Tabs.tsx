/**
 * Tabs.
 *
 * Implements the WAI-ARIA tabs pattern: a roving tabindex, arrow-key movement,
 * and Home/End. Only the selected tab is in the tab order, so Tab moves into
 * the panel rather than through every tab first.
 */

import { useRef, type ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
  badge?: ReactNode;
}

export function Tabs({
  items,
  activeId,
  onChange,
  label,
}: {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const active = items.find((item) => item.id === activeId) ?? items[0];

  function move(delta: number) {
    const index = items.findIndex((item) => item.id === activeId);
    const next = (index + delta + items.length) % items.length;
    onChange(items[next].id);
    // Move focus with the selection, as the ARIA pattern requires.
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>(
      '[role="tab"]',
    );
    buttons?.[next]?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      onChange(items[0].id);
      listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      const last = items.length - 1;
      onChange(items[last].id);
      listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[last]?.focus();
    }
  }

  return (
    <div className="hs-tabs">
      <div
        ref={listRef}
        className="hs-tab-list"
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
      >
        {items.map((item) => {
          const selected = item.id === active?.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`hs-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={`hs-tabpanel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              className={`hs-tab${selected ? " is-active" : ""}`}
              onClick={() => onChange(item.id)}
            >
              {item.label}
              {item.badge != null && (
                <span className="hs-tab-badge">{item.badge}</span>
              )}
            </button>
          );
        })}
      </div>

      {active && (
        <div
          role="tabpanel"
          id={`hs-tabpanel-${active.id}`}
          aria-labelledby={`hs-tab-${active.id}`}
          className="hs-tabpanel"
          tabIndex={0}
        >
          {active.content}
        </div>
      )}
    </div>
  );
}
