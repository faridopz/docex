"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  FileSearch,
  Landmark,
  Layers,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * AppNav — the single shared product navigation.
 *
 * Before this existed, every page hand-rolled its own <header>, so the
 * menu changed shape from screen to screen and features were hard to find.
 * This component is the one source of truth for in-product navigation.
 *
 * Usage:
 *   <AppNav active="compliance">
 *     <button>…page-specific action…</button>   // optional, right slot
 *   </AppNav>
 *
 * `active` highlights the current section. If omitted, it's inferred from
 * the pathname. Deep detail pages (e.g. /verify/[id]) intentionally keep
 * their own contextual "back to X" header instead of this global nav.
 */

export type NavSection =
  | "extract"
  | "attendance"
  | "compliance"
  | "knowledge"
  | "templates";

type NavItem = {
  section: NavSection;
  label: string;
  href: string;
  icon: LucideIcon;
  /** pathname prefixes that should light this item up */
  match: string[];
};

const NAV_ITEMS: NavItem[] = [
  {
    section: "extract",
    label: "Extract",
    href: "/app",
    icon: FileSearch,
    // /app is the generic extraction flow; the sub-award lifecycle shell is
    // one use-case built on it.
    match: ["/app", "/agents/sub-award"],
  },
  {
    section: "attendance",
    label: "Attendance & Payment",
    href: "/agents/attendance-payment",
    icon: Landmark,
    match: ["/agents/attendance-payment", "/rate-cards"],
  },
  {
    section: "compliance",
    label: "Compliance",
    href: "/compliance",
    icon: ShieldCheck,
    // Bank Verify lives under Compliance as a standalone one-off check.
    match: ["/compliance", "/verify"],
  },
  {
    section: "knowledge",
    label: "Knowledge",
    href: "/knowledge",
    icon: BookOpen,
    match: ["/knowledge"],
  },
  {
    section: "templates",
    label: "Templates",
    href: "/templates",
    icon: Layers,
    match: ["/templates"],
  },
];

export function AppNav({
  active,
  children,
}: {
  active?: NavSection;
  children?: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";

  function isActive(item: NavItem): boolean {
    if (active) return item.section === active;
    return item.match.some(
      (m) => pathname === m || pathname.startsWith(m + "/"),
    );
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-100 bg-white/90 shadow-sm backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-6">
        {/* Wordmark — always returns to the landing page */}
        <Link
          href="/"
          className="shrink-0 text-lg font-bold tracking-tight text-brand-600"
        >
          DOCex
        </Link>

        {/* Primary sections */}
        <nav className="hidden flex-1 items-center justify-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => {
            const activeNow = isActive(item);
            return (
              <Link
                key={item.section}
                href={item.href}
                aria-current={activeNow ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  activeNow
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Page-specific action slot */}
        <div className="ml-auto flex shrink-0 items-center gap-2 md:ml-0">
          {children}
        </div>
      </div>

      {/* Mobile section bar — horizontal scroll so nothing is buried */}
      <nav className="flex items-center gap-1 overflow-x-auto border-t border-gray-100 px-4 py-2 md:hidden">
        {NAV_ITEMS.map((item) => {
          const activeNow = isActive(item);
          return (
            <Link
              key={item.section}
              href={item.href}
              aria-current={activeNow ? "page" : undefined}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                activeNow
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-600 hover:bg-gray-50",
              )}
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
