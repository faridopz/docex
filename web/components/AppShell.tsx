"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  CalendarCheck,
  FileSearch,
  Landmark,
  Layers,
  LayoutGrid,
  Loader2,
  LogOut,
  ScrollText,
  Send,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { getOrgProfile } from "@/lib/api";

/**
 * AppShell — the canonical in-product layout: a persistent left sidebar +
 * a slim top bar, with page content in the main column. Replaces the
 * top grouped-dropdown nav inside the app (the marketing landing keeps its
 * own top nav). Built on our existing brand/gray tokens + lucide icons.
 *
 * Usage:
 *   <AppShell active="compliance" actions={<button>…</button>}>
 *     …page content…
 *   </AppShell>
 */

export type NavSection =
  | "extract"
  | "templates"
  | "knowledge"
  | "submit"
  | "compliance"
  | "verify"
  | "attendance";

type NavItem = {
  section: NavSection;
  label: string;
  href: string;
  icon: LucideIcon;
  match: string[];
};

// The three product modules a client can switch on independently. The engine
// underneath is shared; these are just the workflows on top.
export type ModuleKey = "compliance" | "screening" | "knowledge";

type NavGroup = { module: ModuleKey; label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    module: "compliance",
    label: "Compliance & Finance",
    items: [
      { section: "submit", label: "Submit requisition", href: "/compliance/submit", icon: Send, match: ["/compliance/submit"] },
      { section: "compliance", label: "Compliance", href: "/compliance", icon: ShieldCheck, match: ["/compliance"] },
      { section: "verify", label: "Bank Verify", href: "/verify", icon: Landmark, match: ["/verify"] },
      { section: "attendance", label: "Attendance & Payment", href: "/agents/attendance-payment", icon: CalendarCheck, match: ["/agents/attendance-payment", "/rate-cards"] },
    ],
  },
  {
    module: "screening",
    label: "Screening",
    items: [
      { section: "extract", label: "Extract", href: "/app", icon: FileSearch, match: ["/app", "/agents/sub-award"] },
      { section: "templates", label: "Templates", href: "/templates", icon: Layers, match: ["/templates"] },
    ],
  },
  {
    module: "knowledge",
    label: "Knowledge",
    items: [
      { section: "knowledge", label: "Knowledge", href: "/knowledge", icon: BookOpen, match: ["/knowledge"] },
    ],
  },
];

export function AppShell({
  active,
  actions,
  children,
}: {
  active?: NavSection;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { ready, user, signOut } = useAuth();

  // Which modules this org has switched on. Default to all until we know, so
  // nav never flashes empty; if the profile can't load we just show everything.
  const [enabledModules, setEnabledModules] = useState<ModuleKey[]>([
    "compliance",
    "screening",
    "knowledge",
  ]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getOrgProfile();
        if (!cancelled && Array.isArray(p.enabled_modules) && p.enabled_modules.length) {
          setEnabledModules(p.enabled_modules as ModuleKey[]);
        }
      } catch {
        /* keep all modules visible on failure */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = NAV_GROUPS.filter((g) => enabledModules.includes(g.module));
  const complianceOn = enabledModules.includes("compliance");

  // Demo gate: every page rendered inside AppShell requires a signed-in demo
  // user. Public pages (landing, tour, /approve, /checkin) don't use AppShell,
  // so they stay open. We wait for `ready` so we don't redirect on first paint
  // before localStorage has been read.
  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] text-sm text-gray-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading…
      </div>
    );
  }

  function isActive(item: NavItem): boolean {
    return active ? item.section === active : item.match.some((m) => pathname === m || pathname.startsWith(m + "/"));
  }

  return (
    <div className="min-h-screen bg-[#fafaf7] md:flex">
      {/* Sidebar — desktop */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-gray-200 bg-white md:flex">
        <div className="px-5 py-5">
          <Link href="/home" className="block">
            <span className="text-lg font-bold tracking-tight text-brand-600">DOCex</span>
            <span className="mt-0.5 block text-[11px] font-medium uppercase tracking-wide text-gray-400">
              Audit-grade compliance
            </span>
          </Link>
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-2">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const on = isActive(item);
                  return (
                    <Link
                      key={item.section}
                      href={item.href}
                      aria-current={on ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition",
                        on
                          ? "bg-brand-50 text-brand-700"
                          : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                      )}
                    >
                      <item.icon className={cn("h-4 w-4 shrink-0", on ? "text-brand-600" : "text-gray-400")} />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-gray-100 px-3 py-3">
          {complianceOn && (
            <>
              <Link
                href="/compliance/board"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 hover:text-gray-900"
              >
                <LayoutGrid className="h-4 w-4 shrink-0 text-gray-400" />
                Pipeline
              </Link>
              <Link
                href="/compliance/checks"
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 hover:text-gray-900"
              >
                <ScrollText className="h-4 w-4 shrink-0 text-gray-400" />
                Audit log
              </Link>
            </>
          )}
          <Link
            href="/settings/org"
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 hover:text-gray-900"
          >
            <Settings className="h-4 w-4 shrink-0 text-gray-400" />
            Org settings
          </Link>

          <div className="mt-2 flex items-center justify-between gap-2 rounded-lg px-2.5 py-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-gray-700">{user.name}</p>
              <p className="truncate text-[11px] text-gray-400">{user.email}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                signOut();
                router.replace("/login");
              }}
              title="Sign out"
              className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-gray-500 transition hover:bg-gray-50 hover:text-gray-900"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-40 border-b border-gray-100 bg-white/90 backdrop-blur-md">
          {/* Mobile brand + nav */}
          <div className="flex items-center gap-3 px-4 py-2 md:hidden">
            <Link href="/home" className="text-base font-bold tracking-tight text-brand-600">
              DOCex
            </Link>
          </div>
          <div className="flex h-14 items-center justify-end gap-2 px-4 md:px-8">
            {actions}
          </div>
          {/* Mobile horizontal nav */}
          <nav className="flex items-center gap-1 overflow-x-auto border-t border-gray-100 px-3 py-2 md:hidden">
            {groups.flatMap((g) => g.items).map((item) => {
              const on = isActive(item);
              return (
                <Link
                  key={item.section}
                  href={item.href}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                    on ? "bg-brand-50 text-brand-700" : "text-gray-600 hover:bg-gray-50",
                  )}
                >
                  <item.icon className="h-3.5 w-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
