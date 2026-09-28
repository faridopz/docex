"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Banknote,
  BookOpen,
  Home,
  CalendarCheck,
  FileSearch,
  Landmark,
  Layers,
  Scale,
  Timer,
  LayoutGrid,
  Loader2,
  LogOut,
  ScrollText,
  Send,
  Settings,
  ShieldCheck,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import {
  DEFAULT_CLIENT_CONFIG,
  getClientConfig,
  type ClientConfig,
  type ModuleKey,
} from "@/lib/orgConfig";
import { getOnboardingStatus } from "@/lib/onboardingApi";
import { getDocumentPermissions } from "@/lib/requisitionApi";
import { NotificationBell } from "@/components/erp/NotificationBell";

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
  | "dashboard"
  | "requisitions"
  | "advances"
  | "pipeline"
  | "settings"
  | "payments"
  | "audit"
  | "reconciliation"
  | "timesheets"
  | "vouchers"
  | "extract"
  | "templates"
  | "knowledge"
  | "submit"
  | "retire"
  | "compliance"
  | "verify"
  | "attendance";

type NavItem = {
  section: NavSection;
  label: string;
  href: string;
  icon: LucideIcon;
  match: string[];
  // Optional feature flag. When set, this item only appears if the client's
  // profile has that flag on. Items with no flag are part of the base product
  // and every client sees them.
  //
  // This is what lets one engine serve many clients without any of them seeing
  // a menu entry for something their organisation never bought — EVA gets
  // payroll, NEEM does not, and neither is aware of the other's screens.
  flag?: string;
  // Who the item is for. "everyone" is anyone signed in; "money" is the
  // org's finance department(s) and admins (the same people who may see
  // bank details); "approvers" adds anyone with an approving role, so an
  // executive who signs payments can see them; "admin" is administrators
  // only. Defaults to everyone.
  // A programme officer raising a request was shown sixteen items; they use
  // two. Access is still enforced by the server — this is only the menu.
  audience?: "everyone" | "approvers" | "money" | "admin";
};

// The three product modules a client can switch on independently. The engine
// underneath is shared; these are just the workflows on top.
export type { ModuleKey } from "@/lib/orgConfig";

type NavGroup = { module: ModuleKey; label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    module: "compliance",
    label: "Compliance & Finance",
    items: [
      { section: "dashboard", label: "Home", href: "/dashboard", icon: Home, match: ["/dashboard", "/transactions"] },
      // One place for payment requests, with a List ⇄ Board switch on the
      // page. The board used to be a separate "Pipeline" item showing the
      // same records, which made three screens (this, Pipeline, Dashboard)
      // answer the same question.
      { section: "requisitions", label: "Payment requests", href: "/requisitions", icon: Send, match: ["/requisitions"] },
      // Everyone: staff see the advances they must retire (before one stops
      // their next payment); Finance sees everyone's and settles them.
      { section: "advances", label: "Advances", href: "/advances", icon: Wallet, match: ["/advances"], flag: "advance_retirement", audience: "everyone" },
      { section: "payments", label: "Payments", href: "/payments", icon: Banknote, match: ["/payments"] , audience: "approvers" },
      { section: "audit", label: "Audit", href: "/audit", icon: ScrollText, match: ["/audit"] , audience: "approvers" },
      // Month end. Sits next to Audit deliberately: reconciliation is the
      // control that makes the audit trail a description of the bank account
      // rather than a story about it.
      { section: "reconciliation", label: "Reconciliation", href: "/reconciliation", icon: Scale, match: ["/reconciliation"], flag: "bank_reconciliation" , audience: "money" },
      // Effort reporting. Sits in this group rather than an HR one because
      // its output is financial: approved hours decide what each grant is
      // charged for a salary.
      { section: "timesheets", label: "Timesheets", href: "/timesheets", icon: Timer, match: ["/timesheets"], flag: "timesheets" },
      // Participant payment vouchers — the per-diem / event-payment workflow.
      // Flagged with attendance_payments because it is the SAME workflow as the
      // Attendance & Payment screen below: you build a voucher from event
      // participants and their rate cards.
      //
      // It was unflagged, which meant NEEM saw a "New voucher" link for a
      // product they never bought. Worse, it half-worked: the page loads and
      // the rate-card dropdown is empty, because rate cards are configured per
      // organisation and NEEM has none. A dead end in the nav during a client
      // demo reads as a broken system, not an unused feature.
      { section: "vouchers", label: "New voucher", href: "/vouchers/new", icon: Wallet, match: ["/vouchers"], flag: "attendance_payments" , audience: "money" },
      // The pre-requisitions intake screens. "Submit requisition" here and
      // "Requisitions" above were two different systems wearing the same word,
      // which is confusing in a nav and worse in a demo — /requisitions is the
      // one with policy checks, the approval chain and the audit trail.
      //
      // Flagged off by default so new clients see one obvious path. Existing
      // installs that still rely on these screens turn `legacy_intake` on.
      { section: "submit", label: "Submit requisition", href: "/compliance/submit", icon: Send, match: ["/compliance/submit"], flag: "legacy_intake" , audience: "everyone" },
      { section: "retire", label: "Retire advance", href: "/compliance/retire", icon: Wallet, match: ["/compliance/retire"], flag: "legacy_intake" , audience: "everyone" },
      // Compliance (the uploaded policy rulebooks) is set up by an
      // administrator and then runs from inside each payment request, so it
      // lives under Settings rather than in the daily menu.
      { section: "verify", label: "Bank Verify", href: "/verify", icon: Landmark, match: ["/verify"] , audience: "money" , flag: "bank_verification"},
      // Flagged: not every client runs participant-payment events. TA Connect
      // does; a client doing only internal finance ops has no use for it.
      { section: "attendance", label: "Attendance & Payment", href: "/agents/attendance-payment", icon: CalendarCheck, match: ["/agents/attendance-payment", "/rate-cards"], flag: "attendance_payments" , audience: "money" },
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

  // What this client's organisation has switched on — which product modules
  // they bought, and which individual capabilities are enabled inside them.
  // Comes from their profile (profiles/<client>.json), so the same engine
  // presents a different system to each client.
  //
  // Defaults to every module and no features until the call returns: nav never
  // flashes empty, and no capability is ever advertised before we know the
  // client actually has it.
  const [clientConfig, setClientConfig] = useState<ClientConfig>(DEFAULT_CLIENT_CONFIG);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await getClientConfig();
        if (!cancelled) setClientConfig(cfg);
      } catch {
        /* leave the defaults in place — a blip must not empty the nav */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Nudge an admin toward the setup wizard if nobody has configured
  // departments/approval chain yet — a courtesy banner, not a redirect trap
  // (research on setup wizards: don't force users through optional
  // configuration). Dismissible for this browser tab only; it comes back
  // next session until setup is actually run, since the underlying gap is
  // still there.
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  useEffect(() => {
    if (!user || user.role !== "admin") return;
    let cancelled = false;
    (async () => {
      try {
        const status = await getOnboardingStatus();
        if (!cancelled) setNeedsOnboarding(!status.configured);
      } catch {
        /* if the check fails, say nothing rather than nag incorrectly */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  // Whether this person handles money — the server decides from the org's
  // own finance departments. Until it answers, show the everyone-menu only.
  const [handlesMoney, setHandlesMoney] = useState(false);
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getDocumentPermissions()
      .then((p) => {
        if (!cancelled) setHandlesMoney(Boolean(p.handles_money));
      })
      .catch(() => {
        /* the everyone-menu is the safe fallback */
      });
    return () => {
      cancelled = true;
    };
  }, [user]);
  const isAdmin = user?.role === "admin";
  const canSee = (item: NavItem) => {
    const who = item.audience ?? "everyone";
    if (who === "everyone") return true;
    if (who === "admin") return isAdmin;
    if (who === "approvers") return isAdmin || handlesMoney || user?.role === "approver";
    return isAdmin || handlesMoney;
  };

  const enabledModules = clientConfig.modules;
  const groups = NAV_GROUPS
    .filter((g) => enabledModules.includes(g.module))
    // Drop flagged items this client doesn't have, then drop any group that
    // ends up empty — an empty section header is worse than no section.
    .map((g) => ({
      ...g,
      items: g.items.filter(
        (i) => (!i.flag || clientConfig.features[i.flag] === true) && canSee(i),
      ),
    }))
    .filter((g) => g.items.length > 0);


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
          <Link href="/dashboard" className="block">
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
          {/* Pipeline used to sit here, below the divider, next to Security
              and Org settings — a daily working view filed under settings. It
              is now in the working nav directly under Requisitions, where the
              data it shows actually lives.

              "Audit log" also used to sit here pointing at /compliance/checks,
              one nav item above "Audit" (/audit) pointing at the requisition
              audit summary. Two different systems, both called audit, three
              items apart. This is the policy-check history, so it says so —
              and it sits under Compliance, which is the policy area. */}
          {/* One way into settings. There used to be up to eight links here
              for an administrator — org, departments, people, withholding,
              bank accounts, QuickBooks, security, policy history — which
              pushed the working menu off a laptop screen. They live on one
              page now (/settings), grouped by what they are for. */}
          <Link
            href={isAdmin ? "/settings" : "/settings/security"}
            aria-current={pathname.startsWith("/settings") || pathname.startsWith("/compliance/checks") ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition",
              pathname.startsWith("/settings") || pathname.startsWith("/compliance/checks")
                ? "bg-brand-50 text-brand-700"
                : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
            )}
          >
            {isAdmin ? (
              <Settings className="h-4 w-4 shrink-0 text-gray-400" />
            ) : (
              <ShieldCheck className="h-4 w-4 shrink-0 text-gray-400" />
            )}
            {isAdmin ? "Settings" : "Sign-in & security"}
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
          {/* One row on phones: brand left, the page's action and the bell
              right. It used to be two rows, which took a third of a phone
              screen before any content. */}
          <div className="flex h-14 items-center justify-between gap-2 px-4 md:justify-end md:px-8">
            <Link href="/dashboard" className="text-base font-bold tracking-tight text-brand-600 md:hidden">
              DOCex
            </Link>
            <div className="flex min-w-0 items-center gap-2">
              {actions}
              <NotificationBell department={user.department} />
            </div>
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
            {/* On desktop these live in the sidebar footer, which phones don't
                show — so on a phone there was no way to reach Settings or to
                sign out at all. */}
            <Link
              href={isAdmin ? "/settings" : "/settings/security"}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                pathname.startsWith("/settings") ? "bg-brand-50 text-brand-700" : "text-gray-600 hover:bg-gray-50",
              )}
            >
              <Settings className="h-3.5 w-3.5" />
              {isAdmin ? "Settings" : "Security"}
            </Link>
            <button
              type="button"
              onClick={() => {
                signOut();
                router.replace("/login");
              }}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </nav>
        </header>

        {needsOnboarding && !bannerDismissed && !pathname.startsWith("/onboarding") && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-100 bg-brand-50 px-4 py-2.5 text-sm md:px-8">
            <span className="text-brand-800">
              <strong className="font-semibold">Finish setting up your organisation</strong>{" "}
              — departments and your approval chain aren't configured yet.
            </span>
            <span className="flex items-center gap-3">
              <Link href="/onboarding" className="font-semibold text-brand-700 hover:text-brand-900">
                Set up now
              </Link>
              <button
                type="button"
                onClick={() => setBannerDismissed(true)}
                className="text-xs text-brand-600 hover:text-brand-800"
              >
                Later
              </button>
            </span>
          </div>
        )}
        {/* Phones get a side gutter; from sm: up each page keeps its own
            layout. Several pages had none, so text ran to the screen edge. */}
        <main className="flex-1 px-4 sm:px-0">{children}</main>
      </div>
    </div>
  );
}
