"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CalendarCheck,
  Clock,
  FileSearch,
  Inbox,
  Landmark,
  Layers,
  Plus,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { listChecks } from "@/lib/api";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
  type CheckSummary,
} from "@/types";

/**
 * /home — the in-product launcher, re-skinned to the Stitch layout: grouped
 * capability tiles (each with a primary action) plus a Recent Activity rail.
 * Wrapped in the left-sidebar AppShell.
 */

type Tile = {
  icon: LucideIcon;
  name: string;
  blurb: string;
  href: string;
  cta: string;
  primary?: boolean;
};

const GROUPS: { label: string; tiles: Tile[] }[] = [
  {
    label: "Documents",
    tiles: [
      { icon: FileSearch, name: "Extract", blurb: "Answer questions across a stack of documents — with source, quote, and confidence.", href: "/app", cta: "Start an extraction", primary: true },
      { icon: Layers, name: "Templates", blurb: "Save and reuse the questions your team asks every time.", href: "/templates", cta: "Open the library" },
      { icon: BookOpen, name: "Knowledge", blurb: "Ask your document library a question and get a cited answer.", href: "/knowledge", cta: "Open knowledge" },
    ],
  },
  {
    label: "Payments & Compliance",
    tiles: [
      { icon: ShieldCheck, name: "Compliance", blurb: "Check a payment against one or more policy sets, with an audit trail.", href: "/compliance/check", cta: "Check a payment", primary: true },
      { icon: Landmark, name: "Bank Verify", blurb: "A one-off check: confirm a recipient's name matches the bank record.", href: "/verify/new", cta: "Run a check" },
      { icon: CalendarCheck, name: "Attendance & Payment", blurb: "Turn an attendance log + payment list into a verified schedule.", href: "/agents/attendance-payment", cta: "Open the flow" },
    ],
  },
];

export default function HomePage() {
  const [recent, setRecent] = useState<CheckSummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const checks = await listChecks();
        if (!cancelled) setRecent(checks.slice(0, 6));
      } catch {
        if (!cancelled) setRecent([]); // fail soft → quiet state
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell
      actions={
        <Link
          href="/compliance/check"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-3.5 w-3.5" />
          New check
        </Link>
      }
    >
      <div className="mx-auto max-w-6xl px-6 py-8 md:px-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            What would you like to do?
          </h1>
          <p className="mt-2 text-base text-gray-600">
            Pick a tool to begin your audit-ready workflow.
          </p>
        </header>

        <div className="grid gap-8 lg:grid-cols-3">
          {/* Capability tiles */}
          <div className="space-y-8 lg:col-span-2">
            {GROUPS.map((group) => (
              <section key={group.label}>
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
                  {group.label}
                </h2>
                <div className="grid gap-4 sm:grid-cols-3">
                  {group.tiles.map((t) => (
                    <div
                      key={t.name}
                      className="flex flex-col rounded-2xl border border-gray-200 bg-white p-5 shadow-sm"
                    >
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                        <t.icon className="h-5 w-5" />
                      </div>
                      <h3 className="mt-3 text-base font-semibold text-gray-900">{t.name}</h3>
                      <p className="mt-1 flex-1 text-xs leading-relaxed text-gray-600">{t.blurb}</p>
                      <Link
                        href={t.href}
                        className={
                          "mt-4 inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition " +
                          (t.primary
                            ? "bg-brand-600 text-white shadow-sm hover:bg-brand-700"
                            : "border border-gray-200 bg-white text-gray-700 hover:border-brand-300 hover:text-brand-700")
                        }
                      >
                        {t.cta}
                        {t.primary && <ArrowRight className="h-3.5 w-3.5" />}
                      </Link>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          {/* Recent activity rail */}
          <aside className="lg:col-span-1">
            <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-900">Recent activity</h2>
                <Clock className="h-4 w-4 text-gray-400" />
              </div>

              {recent === null ? (
                <div className="mt-4 space-y-2">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="h-12 animate-pulse rounded-lg bg-gray-100" />
                  ))}
                </div>
              ) : recent.length === 0 ? (
                <div className="flex flex-col items-center px-2 py-12 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-400">
                    <Inbox className="h-6 w-6" />
                  </div>
                  <p className="mt-3 text-sm font-semibold text-gray-900">Quiet for now</p>
                  <p className="mt-1 text-xs text-gray-500">
                    Your compliance checks and reports will appear here as you work.
                  </p>
                </div>
              ) : (
                <div className="mt-3 space-y-1">
                  {recent.map((c) => (
                    <Link
                      key={c.payment_id}
                      href={`/compliance/checks/${c.payment_id}`}
                      className="group flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-gray-50"
                    >
                      <span className={"h-2 w-2 shrink-0 rounded-full " + overallVerdictDot[c.overall_verdict]} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-gray-900">
                          {c.payment_label}
                        </span>
                        <span className="block text-[11px] text-gray-400">{c.rulebook_name}</span>
                      </span>
                      <span
                        className={
                          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium " +
                          overallVerdictColor[c.overall_verdict]
                        }
                      >
                        {overallVerdictLabel[c.overall_verdict]}
                      </span>
                    </Link>
                  ))}
                  <Link
                    href="/compliance/checks"
                    className="mt-2 block px-2 text-xs font-medium text-brand-700 hover:underline"
                  >
                    View all checks →
                  </Link>
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
