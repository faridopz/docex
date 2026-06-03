"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  CalendarCheck,
  ChevronDown,
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
 * Capabilities are grouped the way users actually think about them:
 *   • Documents            — read & answer documents
 *   • Payments & Compliance — check, verify, and pay
 *
 * Desktop shows two grouped dropdown menus; mobile shows a single grouped
 * scroll bar so every capability (including the standalone Bank Verify
 * one-off check) stays one tap away. Deep detail pages keep their own
 * contextual "back to X" header instead of this global nav.
 *
 * `active` is accepted for back-compat but navigation highlighting is
 * driven primarily by the current pathname.
 */

export type NavSection =
  | "extract"
  | "templates"
  | "knowledge"
  | "compliance"
  | "verify"
  | "attendance";

type NavItem = {
  section: NavSection;
  label: string;
  href: string;
  icon: LucideIcon;
  desc: string;
  match: string[];
};

type NavGroup = { label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Documents",
    items: [
      {
        section: "extract",
        label: "Extract",
        href: "/app",
        icon: FileSearch,
        desc: "Answer questions across a stack of documents",
        match: ["/app", "/agents/sub-award"],
      },
      {
        section: "templates",
        label: "Templates",
        href: "/templates",
        icon: Layers,
        desc: "Reusable question sets for every batch",
        match: ["/templates"],
      },
      {
        section: "knowledge",
        label: "Knowledge",
        href: "/knowledge",
        icon: BookOpen,
        desc: "Ask your document library, with citations",
        match: ["/knowledge"],
      },
    ],
  },
  {
    label: "Payments & Compliance",
    items: [
      {
        section: "compliance",
        label: "Compliance",
        href: "/compliance",
        icon: ShieldCheck,
        desc: "Check payments against your policy sets",
        match: ["/compliance"],
      },
      {
        section: "verify",
        label: "Bank Verify",
        href: "/verify",
        icon: Landmark,
        desc: "One-off bank account name checks",
        match: ["/verify"],
      },
      {
        section: "attendance",
        label: "Attendance & Payment",
        href: "/agents/attendance-payment",
        icon: CalendarCheck,
        desc: "Attendance to a verified payment schedule",
        match: ["/agents/attendance-payment", "/rate-cards"],
      },
    ],
  },
];

function matchesPath(item: NavItem, pathname: string): boolean {
  return item.match.some((m) => pathname === m || pathname.startsWith(m + "/"));
}

export function AppNav({
  active,
  children,
}: {
  active?: NavSection;
  children?: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const navRef = useRef<HTMLDivElement | null>(null);

  // Close any open dropdown on outside click, escape, or route change.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenGroup(null);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenGroup(null);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);
  useEffect(() => setOpenGroup(null), [pathname]);

  function isItemActive(item: NavItem): boolean {
    return active ? item.section === active : matchesPath(item, pathname);
  }
  function isGroupActive(group: NavGroup): boolean {
    return group.items.some(isItemActive);
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-100 bg-white/90 shadow-sm backdrop-blur-md">
      <div
        ref={navRef}
        className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-6"
      >
        <Link
          href="/home"
          className="shrink-0 text-lg font-bold tracking-tight text-brand-600"
        >
          DOCex
        </Link>

        {/* Grouped dropdown menus — desktop */}
        <nav className="hidden flex-1 items-center gap-1 md:flex">
          {NAV_GROUPS.map((group) => {
            const open = openGroup === group.label;
            const groupActive = isGroupActive(group);
            return (
              <div key={group.label} className="relative">
                <button
                  type="button"
                  onClick={() =>
                    setOpenGroup((g) => (g === group.label ? null : group.label))
                  }
                  aria-expanded={open}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                    groupActive || open
                      ? "bg-brand-50 text-brand-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                  )}
                >
                  {group.label}
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 transition-transform",
                      open && "rotate-180",
                    )}
                  />
                </button>

                {open && (
                  <div className="absolute left-0 top-full z-50 mt-1.5 w-72 overflow-hidden rounded-xl border border-gray-200 bg-white p-1.5 shadow-lg">
                    {group.items.map((item) => {
                      const itemActive = isItemActive(item);
                      return (
                        <Link
                          key={item.section}
                          href={item.href}
                          className={cn(
                            "flex items-start gap-3 rounded-lg p-2.5 transition",
                            itemActive
                              ? "bg-brand-50"
                              : "hover:bg-gray-50",
                          )}
                        >
                          <span
                            className={cn(
                              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                              itemActive
                                ? "bg-brand-600 text-white"
                                : "bg-gray-100 text-gray-600",
                            )}
                          >
                            <item.icon className="h-4 w-4" />
                          </span>
                          <span className="min-w-0">
                            <span
                              className={cn(
                                "block text-sm font-medium",
                                itemActive ? "text-brand-700" : "text-gray-900",
                              )}
                            >
                              {item.label}
                            </span>
                            <span className="block text-xs leading-snug text-gray-500">
                              {item.desc}
                            </span>
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Page-specific action slot */}
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {children}
        </div>
      </div>

      {/* Mobile — grouped horizontal scroll bar */}
      <div className="flex items-center gap-3 overflow-x-auto border-t border-gray-100 px-4 py-2 md:hidden">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex shrink-0 items-center gap-1">
            <span className="px-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
              {group.label.split(" ")[0]}
            </span>
            {group.items.map((item) => {
              const itemActive = isItemActive(item);
              return (
                <Link
                  key={item.section}
                  href={item.href}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                    itemActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-gray-600 hover:bg-gray-50",
                  )}
                >
                  <item.icon className="h-3.5 w-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </div>
    </header>
  );
}
