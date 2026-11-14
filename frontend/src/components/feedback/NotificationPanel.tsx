/**
 * Notification centre foundation.
 *
 * There is no notification backend yet, so this renders the real UI shell and
 * says so. It does not invent notifications, unread counts or delivery state —
 * the unread badge only appears when a count is actually supplied by a caller,
 * which today never happens.
 *
 * The shape is what a real feed needs: list, read/unread, timestamps, source
 * attribution and priority. Wiring it to an API later means passing data in,
 * not rebuilding the component.
 */

import { useEffect, useRef, useState } from "react";
import { Bell, BellOff } from "../ui/icons";
import { EmptyState, ErrorState, LoadingState } from "../feedback/States";

export interface NotificationItem {
  id: string;
  title: string;
  body?: string;
  /** Where it came from, e.g. "Jira" or "Canary Labs". */
  source?: string;
  timestamp: string;
  read: boolean;
  priority?: "low" | "normal" | "high";
}

interface NotificationPanelProps {
  /** Real notifications. Omitted while no API exists, which is the honest state. */
  items?: NotificationItem[];
  loading?: boolean;
  error?: unknown;
  onMarkAllRead?: () => void;
  onSelect?: (item: NotificationItem) => void;
  /** True when the backend for this feed does not exist yet. */
  unavailable?: boolean;
}

export default function NotificationPanel({
  items,
  loading,
  error,
  onMarkAllRead,
  onSelect,
  unavailable,
}: NotificationPanelProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unread = items?.filter((item) => !item.read).length ?? 0;

  return (
    <div className="hs-notif" ref={ref}>
      <button
        type="button"
        className="hs-icon-btn"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={
          unread > 0 ? `Notifications, ${unread} unread` : "Notifications"
        }
      >
        <Bell size={16} aria-hidden="true" />
        {unread > 0 && (
          <span className="hs-notif-badge" aria-hidden="true">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="hs-notif-panel" role="dialog" aria-label="Notifications">
          <div className="hs-notif-head">
            <span>Notifications</span>
            {items && items.length > 0 && onMarkAllRead && (
              <button type="button" className="hs-link-btn" onClick={onMarkAllRead}>
                Mark all read
              </button>
            )}
          </div>

          <div className="hs-notif-body">
            {loading ? (
              <div style={{ padding: 14 }}>
                <LoadingState rows={3} compact />
              </div>
            ) : error ? (
              <div style={{ padding: 14 }}>
                <ErrorState
                  compact
                  title="Could not load notifications"
                  description={error instanceof Error ? error.message : undefined}
                />
              </div>
            ) : unavailable ? (
              <div style={{ padding: 14 }}>
                <div className="hs-notif-unavailable">
                  <BellOff size={16} aria-hidden="true" />
                  <div>
                    <p className="hs-state-title">No notification feed yet</p>
                    <p className="hs-state-desc">
                      Notifications arrive with the Work Intelligence layer. This
                      panel is the shell they will render into.
                    </p>
                  </div>
                </div>
              </div>
            ) : !items || items.length === 0 ? (
              <div style={{ padding: 14 }}>
                <EmptyState
                  compact
                  title="You are all caught up"
                  description="Nothing needs your attention right now."
                />
              </div>
            ) : (
              <ul className="hs-notif-list">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={`hs-notif-item${item.read ? "" : " is-unread"}`}
                      onClick={() => onSelect?.(item)}
                    >
                      <span className="grow">
                        <span className="hs-notif-title">{item.title}</span>
                        {item.body && (
                          <span className="hs-notif-text">{item.body}</span>
                        )}
                        <span className="hs-notif-meta">
                          {item.source && <span>{item.source}</span>}
                          <time dateTime={item.timestamp}>
                            {new Date(item.timestamp).toLocaleString()}
                          </time>
                          {item.priority === "high" && (
                            <span className="hs-notif-priority">High</span>
                          )}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
