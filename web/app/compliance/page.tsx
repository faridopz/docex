"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ChevronRight,
  FileCheck,
  FileSearch,
  FileText,
  Inbox,
  Landmark,
  Loader2,
  Plus,
  Sparkles,
  Stamp,
} from "lucide-react";
import { listChecks, listRulebooks } from "@/lib/api";
import { AppNav } from "@/components/AppNav";
import { GuidanceCard } from "@/components/GuidanceCard";
import type { CheckSummary, RulebookSummary } from "@/types";

/**
 * Compliance landing — the rulebooks list.
 *
 * The persistent asset in Compliance Check is the rulebook (an interpreted
 * policy). This page is the front door: see what you've already loaded,
 * jump back into any of them, or upload a new policy.
 *
 * UX choices:
 *  - Empty state is the FIRST visit experience. It gets the most love —
 *    a Sparkles-led CTA, copy that frames the first upload as the start of
 *    a journey ("Upload your first policy"), and an explanation of why
 *    rulebooks are reusable ("Upload once, run checks forever").
 *  - Populated state shows rule counts and last-updated time on each card
 *    so the officer can recognise rulebooks at a glance without opening them.
 *  - Whole card is the click target — Fitts's law. No competing buttons.
 */

export default function ComplianceListPage() {
  const [rulebooks, setRulebooks] = useState<RulebookSummary[] | null>(null);
  const [checks, setChecks] = useState<CheckSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Load rulebooks and checks in parallel — the stats widget needs
        // both. If checks fail (older deployments without the endpoint),
        // it's a non-fatal warning; rulebooks are the primary content.
        const [rbList, checksList] = await Promise.allSettled([
          listRulebooks(),
          listChecks(),
        ]);
        if (cancelled) return;
        if (rbList.status === "fulfilled") {
          setRulebooks(rbList.value);
        } else {
          setError(
            rbList.reason instanceof Error
              ? rbList.reason.message
              : "Could not load rulebooks. Is the API running on port 8000?",
          );
          return;
        }
        if (checksList.status === "fulfilled") {
          setChecks(checksList.value);
        } else {
          // Checks endpoint missing — non-fatal, just hide the stats widget.
          setChecks([]);
        }
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load rulebooks. Is the API running on port 8000?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = {
    rulebooks: rulebooks?.length ?? 0,
    checks: checks?.length ?? 0,
    approved: checks?.filter((c) => c.approved).length ?? 0,
  };

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <AppNav active="compliance">
        <Link
          href="/compliance/pending"
          className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
          title="Open the pending inbox — checks awaiting your decision"
        >
          <Inbox className="h-3.5 w-3.5" />
          Inbox
        </Link>
        <Link
          href="/compliance/checks"
          className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
          title="View saved checks + approved PVs archive"
        >
          <FileSearch className="h-3.5 w-3.5" />
          Saved checks
        </Link>
        <Link
          href="/compliance/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-3.5 w-3.5" />
          New rulebook
        </Link>
      </AppNav>

      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="space-y-8">
          {/* Page header */}
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Your internal auditor, automated.
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                DOCex reads your procurement, travel, or donor policy and
                turns it into a rulebook. Every payment voucher gets checked
                rule by rule, with citations from both the policy and the
                payment.{" "}
                <span className="text-gray-900">
                  Upload your policy once. Audit-grade checks forever.
                </span>
              </p>
            </div>
            {rulebooks && rulebooks.length > 0 && (
              <Link
                href="/compliance/new"
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              >
                <Plus className="h-4 w-4" />
                New rulebook
              </Link>
            )}
          </div>

          {/* "DOCex is working" stats — visible the moment there's anything
              to show. Anchors the orchestrator framing: this isn't a chatbot
              you visit, it's infrastructure with a track record. */}
          {rulebooks && rulebooks.length > 0 && stats.checks > 0 && (
            <div className="grid gap-3 sm:grid-cols-3">
              <Link
                href="/compliance/checks"
                className="group rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
              >
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-600">
                  <FileSearch className="h-4 w-4 text-brand-600" />
                  Total checks
                </div>
                <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900 transition-colors group-hover:text-brand-700">
                  {stats.checks}
                </p>
                <p className="mt-1 text-[11px] text-gray-500">
                  Saved automatically with stable URLs
                </p>
              </Link>
              <Link
                href="/compliance/checks?filter=approved"
                className="group rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 transition hover:border-emerald-300 hover:shadow-card-hover"
              >
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-emerald-700">
                  <Stamp className="h-4 w-4" />
                  Approved
                </div>
                <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900">
                  {stats.approved}
                </p>
                <p className="mt-1 text-[11px] text-emerald-700/80">
                  Your audit-ready archive
                </p>
              </Link>
              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-600">
                  <FileCheck className="h-4 w-4 text-brand-600" />
                  Rulebooks
                </div>
                <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900">
                  {stats.rulebooks}
                </p>
                <p className="mt-1 text-[11px] text-gray-500">
                  Policies interpreted and ready to check against
                </p>
              </div>
            </div>
          )}

          {/* Standalone compliance utility — a one-off bank account check
              that lives under Compliance but doesn't need a rulebook. */}
          <Link
            href="/verify/new"
            className="group flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
              <Landmark className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-gray-900 group-hover:text-brand-700">
                Bank account check
              </p>
              <p className="mt-0.5 text-xs text-gray-500">
                One-off verification — confirm a recipient&apos;s name matches
                the bank-of-record holder before money moves. No rulebook needed.
              </p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-gray-300 transition group-hover:translate-x-0.5 group-hover:text-brand-600" />
          </Link>

          {/* Always-visible guidance for first-time users */}
          {rulebooks && rulebooks.length > 0 && (
            <GuidanceCard title="How this works">
              Pick a rulebook to edit it, or run a check against it. Drop in a
              payment voucher with its receipts and invoices — DOCex returns a
              verdict for every rule with citations from both the policy and
              the payment.
            </GuidanceCard>
          )}

          {/* Error state */}
          {error && (
            <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium text-red-900">Could not load rulebooks</p>
              <p>{error}</p>
              <p className="text-xs text-red-600">
                Check the backend is running: <code className="rounded bg-red-100 px-1 py-0.5">uvicorn api.main:app --reload --port 8000</code>
              </p>
            </div>
          )}

          {/* Loading state — only show while we have no data and no error */}
          {rulebooks === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading rulebooks…
            </div>
          )}

          {/* Empty state */}
          {rulebooks !== null && rulebooks.length === 0 && !error && <EmptyState />}

          {/* Populated state */}
          {rulebooks !== null && rulebooks.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {rulebooks.map((rb) => (
                <RulebookCard key={rb.id} rb={rb} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

/* ─── Empty state ───────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <FileCheck className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        No rulebooks yet
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Upload your own procurement, travel, or expense policy — or start
        with our pre-built sample so you can see the full flow in 60 seconds.
      </p>
      <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Link
          href="/compliance/rulebooks/sample-ngo-procurement"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700"
        >
          <Sparkles className="h-4 w-4" />
          Try the sample rulebook
        </Link>
        <Link
          href="/compliance/new"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          <FileText className="h-4 w-4" />
          Upload your own policy
        </Link>
      </div>
      <p className="mt-4 text-xs text-gray-400">
        Sample: Standard NGO Procurement Policy · 10 rules · pre-loaded for demo
      </p>
    </div>
  );
}

/* ─── Card ─────────────────────────────────────────────────────────────── */

function RulebookCard({ rb }: { rb: RulebookSummary }) {
  const updated = rb.updated_at ? new Date(rb.updated_at) : null;
  const docCount = rb.source_documents.length;
  const inactive = rb.rule_count - rb.active_rule_count;

  return (
    <Link
      href={`/compliance/rulebooks/${rb.id}`}
      // Whole card is the click target — Fitts's law. The chevron on the
      // right is a visual affordance, not a separate hit area.
      className="group block rounded-xl border border-gray-200 bg-white p-5 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
            {rb.name}
          </h3>
          <p
            className="mt-1 flex items-center gap-1.5 text-xs text-gray-500"
            title={rb.source_documents.join(", ")}
          >
            <FileText className="h-3 w-3 shrink-0" />
            <span className="truncate">
              {docCount === 1
                ? rb.source_documents[0]
                : `${docCount} source documents`}
            </span>
          </p>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          {rb.active_rule_count} active{" "}
          {rb.active_rule_count === 1 ? "rule" : "rules"}
        </span>
        {inactive > 0 && (
          <span className="text-xs text-gray-500">
            {inactive} inactive
          </span>
        )}
        {updated && (
          <span className="ml-auto text-xs text-gray-400">
            Updated {formatRelative(updated)}
          </span>
        )}
      </div>
    </Link>
  );
}

/**
 * Human-friendly relative time. Recency cues land harder than absolute
 * dates for cards the user scans rather than reads.
 */
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
