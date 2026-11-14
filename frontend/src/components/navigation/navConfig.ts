/**
 * Primary navigation.
 *
 * Single source of truth for the product's top-level areas. The sidebar, the
 * mobile drawer and the command palette all read from this, so a route can
 * never appear in one place and be missing from another.
 */

import {
  AppWindow,
  Bot,
  BookOpen,
  Home,
  LayoutGrid,
  Shield,
  Target,
  type LucideIcon,
} from "../ui/icons";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Short description, used by the command palette. */
  description: string;
  /** Marks areas whose backend is not built yet, so the UI can say so. */
  pending?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: "Work",
    items: [
      {
        to: "/today",
        label: "Today",
        icon: Home,
        description: "Everything needing your attention today",
      },
      {
        to: "/copilot",
        label: "Copilot",
        icon: Bot,
        description: "Ask questions and direct the Brain",
        pending: true,
      },
      {
        to: "/missions",
        label: "Missions",
        icon: Target,
        description: "Goal-driven work executed end to end",
        pending: true,
      },
    ],
  },
  {
    label: "Intelligence",
    items: [
      {
        to: "/workforce",
        label: "Workforce",
        icon: LayoutGrid,
        description: "Specialized AI workers and their activity",
        pending: true,
      },
      {
        to: "/memory",
        label: "Memory",
        icon: BookOpen,
        description: "Unified company knowledge and context",
        pending: true,
      },
    ],
  },
  {
    label: "Platform",
    items: [
      {
        to: "/apps",
        label: "Apps",
        icon: AppWindow,
        description: "Connected applications and integrations",
      },
      {
        to: "/governance",
        label: "Governance",
        icon: Shield,
        description: "Approvals, policy and audit",
        pending: true,
      },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

/** Resolve the nav item that owns a pathname, for the header title. */
export function findNavItem(pathname: string): NavItem | null {
  const exact = ALL_NAV_ITEMS.find((item) => item.to === pathname);
  if (exact) return exact;
  // Longest-prefix match, so /apps/marketplace still highlights "Apps".
  return (
    ALL_NAV_ITEMS.filter(
      (item) => item.to !== "/" && pathname.startsWith(`${item.to}/`),
    ).sort((a, b) => b.to.length - a.to.length)[0] ?? null
  );
}
