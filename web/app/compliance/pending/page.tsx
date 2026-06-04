"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  HelpCircle,
  Inbox,
  Loader2,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { listPendingChecks } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import {
  overallVerdictColor,
  overallVerdictDot,
  overallVerdictLabel,
  type CheckSummary,
  type OverallVerdict,
} from "@/types";

/**
 * Pending Inbox — every compliance check that isn't yet approved.
 *
 * This is the page a compliance officer opens to start their morning:
 *   "what needs my attention today?"
 *
 * Two views:
 *   - Awaiting decision: checks with no outstanding question — the
 *     officer reviews evidence and approves / escalates / clarifies.
 *   - Awaiting reply: checks where the officer has already asked
 *     someone for clarification and is waiting for a response.
 *
 * Each row jumps straight into the check detail page, where the
 * approval-chain panel exposes Escalate / Request clarification /
 * Respond / Approve.
 *
 * Post-Supabase: this will filter to the logged-in user's queue.
 * Pre-auth: it shows the whole org's unapproved queue.
 */
type Tab = "decision" | "reply" | "all";

const TABS: { id: Tab; label: string; hint: string }[] = [
  {
    id: "decision",
    label: "Awaiting decision",
    hint: "No open question — your move",
  },
  {
    id: "reply",
    label: "Awaiting reply",
    hint: "Waiting on someone to answer your question",
  },
  { id: "all", label: "Everything pending", hint: "All unapproved checks" },
];

export default function PendingInboxPage() {
  const [checks, setChecks] = useState<CheckSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("decision");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listPendingChecks();
        if (!cancelled) setChecks(list);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the pending inbox. Is the API running?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const counts = useMemo(() => {
    if (!checks) return { decision: 0, reply: 0, all: 0 };
    return {
      decision: checks.filter((c) => !c.pending_question).length,
      reply: checks.filter((c) => !!c.pending_question).length,
      all: checks.length,
    };
  }, [checks]);

  const filtered = useMemo(() => {
    if (!checks) return [];
    switch (tab) {
      case "decision":
        return checks.filter((c) => !c.pending_question);
      case "reply":
        return checks.filter((c) => !!c.pending_question);
      default:
        return checks;
    }
  }, [checks, tab]);

  return (
    <AppShell
      active="compliance"
      actions={
        <Link
          href="/compliance/checks"
          className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          All checks
        </Link>
      }
    >
      <main className="mx-auto max-w-5xl space-y-8 px-6 py-10">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            Pending inbox
          </h1>
          <p className="mt-2 max-w-2xl text-base text-gray-600">
            Every compliance check that isn't yet approved.{" "}
            <span className="font-semibold text-gray-900">
              Start with "awaiting decision" — those are the ones blocked on
              you.
            </span>
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <p className="font-medium text-red-900">Could not load inbox</p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {checks === null && !error && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        )}

        {checks !== null && checks.length === 0 && !error && <EmptyState />}

        {checks !== null && checks.length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {TABS.map((t) => (
                <FilterChip
                  key={t.id}
                  active={tab === t.id}
                  onClick={() => setTab(t.id)}
                  label={t.label}
                  hint={t.hint}
                  count={
                    t.id === "decision"
                      ? counts.decision
                      : t.id === "reply"
                        ? counts.reply
                        : counts.all
                  }
                />
              ))}
            </div>

            {filtered.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-500">
                Nothing here. Nice work.
              </div>
            ) : (
              <div className="space-y-2">
                {filtered.map((c) => (
                  <CheckRow key={c.payment_id} check={c} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </AppShell>
  );
}

/* ─── Empty state ─────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
        <UserCheck className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        Inbox zero
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Every compliance check has been approved. New checks land here the
        moment they're run.
      </p>
      <Link
        href="/compliance"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
      >
        Run a new check
      </Link>
    </div>
  );
}

/* ─── Filter chip ─────────────────────────────────────────────────────── */

function FilterChip({
  active,
  onClick,
  label,
  hint,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition ${
        active
          ? "bg-brand-600 text-white shadow-sm"
          : "border border-gray-200 bg-white text-gray-700 hover:border-brand-300 hover:text-brand-700"
      }`}
    >
      {label}
      <span
        className={`inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums ${
          active ? "bg-white/20" : "bg-gray-100 text-gray-600"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

/* ─── Check row ───────────────────────────────────────────────────────── */

function CheckRow({ check }: { check: CheckSummary }) {
  const created = check.created_at ? new Date(check.created_at) : null;

  return (
    <Link
      href={`/compliance/checks/${check.payment_id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
              {check.payment_label}
            </h3>
            <VerdictPill verdict={check.overall_verdict} />
            {check.pending_with && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200">
                Sitting with {check.pending_with}
              </span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-gray-600">
            {check.overall_summary}
          </p>
          {check.pending_question && (
            <div className="rounded-lg bg-blue-50/60 px-3 py-2 ring-1 ring-blue-200">
              <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-blue-700">
                <HelpCircle className="h-3 w-3" />
                Outstanding question
              </p>
              <p className="mt-0.5 text-sm text-gray-800">
                {check.pending_question}
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <span>{check.rulebook_name}</span>
            <span>
              {check.document_count}{" "}
              {check.document_count === 1 ? "document" : "documents"}
            </span>
            {created && <span>{formatRelative(created)}</span>}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>
    </Link>
  );
}

function VerdictPill({ verdict }: { verdict: OverallVerdict }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${overallVerdictColor[verdict]}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${overallVerdictDot[verdict]}`}
      />
      {overallVerdictLabel[verdict]}
    </span>
  );
}

function formatRelative(d: Date): string {
  const diff = Date.now() - d.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}
