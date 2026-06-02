"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ClipboardCheck,
  FileSearch,
  Landmark,
  Loader2,
  Mail,
  ScrollText,
  Sparkles,
  Users,
} from "lucide-react";
import {
  listChecks,
  listRulebooks,
  listVerifyBatches,
} from "@/lib/api";
import { GuidanceCard } from "@/components/GuidanceCard";
import type {
  BatchVerifySummary,
  CheckSummary,
  RulebookSummary,
} from "@/types";

/**
 * /agents/sub-award — Abosede's full workflow as one branded agent.
 *
 * This is DOCex's second composite agent. Unlike the Attendance Payment
 * Agent (which has its own engine), the Sub-award Co-Pilot is a *lifecycle
 * shell* over existing primitives:
 *
 *   1. Screen applicants             → Extraction (sub-award template)
 *   2. Award decision                → human-only step (we surface, not decide)
 *   3. Verify grantee bank accounts  → Bank Verify (purpose=grantee_disbursement)
 *   4. Receive quarterly reports     → Extraction (quarterly review template)
 *   5. Follow up on gaps             → existing draft-followups flow
 *
 * Each step links into the primitive pre-filled with the right context
 * (template id, purpose tag) so the user doesn't have to remember which
 * settings to pick. Live counts on each card make this also a
 * dashboard — Abosede opens this page and immediately sees where she is.
 */

export default function SubAwardAgentPage() {
  const [verifyCount, setVerifyCount] = useState<number | null>(null);
  const [verifyGranteeCount, setVerifyGranteeCount] = useState<number | null>(null);
  const [rulebookCount, setRulebookCount] = useState<number | null>(null);
  const [checkApprovedCount, setCheckApprovedCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [batches, rulebooks, checks] = await Promise.allSettled([
          listVerifyBatches(),
          listRulebooks(),
          listChecks(),
        ]);
        if (cancelled) return;
        if (batches.status === "fulfilled") {
          setVerifyCount(batches.value.length);
          setVerifyGranteeCount(
            batches.value.filter((b: BatchVerifySummary) => b.purpose === "grantee_disbursement").length,
          );
        }
        if (rulebooks.status === "fulfilled") {
          setRulebookCount(rulebooks.value.length);
        }
        if (checks.status === "fulfilled") {
          setCheckApprovedCount(
            (checks.value as CheckSummary[]).filter((c) => c.approved).length,
          );
        }
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load agent dashboard. Is the API running?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-6 px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <Sparkles className="h-4 w-4 text-brand-600" />
            Sub-award Co-Pilot
          </span>
          <div className="flex items-center gap-2">
            <Link
              href="/agents/attendance-payment"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
            >
              Attendance Agent
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="space-y-8">
          {/* Hero */}
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Sub-award Co-Pilot
            </h1>
            <p className="mt-2 max-w-2xl text-base text-gray-600">
              The whole grantee lifecycle in one place — from initial
              application screening, through bank-verified disbursement, to
              quarterly report review. Each step uses DOCex's underlying
              primitives, pre-configured for sub-award work.
            </p>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          <GuidanceCard title="How this agent works">
            Each step below links into the primitive that powers it —
            <span className="font-medium"> pre-configured</span> with the
            right template, purpose tag, and column expectations. You can
            also use the primitives directly from their own URLs; this page
            is the front door for the workflow Abosede actually runs.
          </GuidanceCard>

          {/* Lifecycle steps */}
          <div className="space-y-3">
            <Step
              number={1}
              title="Screen applicants"
              description="Drop in every applicant's documents — CAC registration, proposal, audit reports — and DOCex answers your standard questions in an Excel table."
              icon={<FileSearch className="h-5 w-5" />}
              href="/app?template=sub-award-screening"
              cta="Open screening"
              count={null}
              countLabel=""
            />

            <Step
              number={2}
              title="Award decision"
              description="Human step. Review the screening bucket assignments, pick your awardees, send notifications. DOCex surfaces the data — the decision stays with you and the panel."
              icon={<ClipboardCheck className="h-5 w-5" />}
              href={null}
              cta="Manual"
              count={null}
              countLabel=""
              muted
            />

            <Step
              number={3}
              title="Verify grantee bank accounts"
              description="Before any disbursement, run the awardees' bank details through Bank Verify with purpose=grantee_disbursement. Catches typos and wrong-person attacks before money moves."
              icon={<Landmark className="h-5 w-5" />}
              href="/verify/new"
              cta="Verify accounts"
              count={verifyGranteeCount}
              countLabel="grantee batches"
            />

            <Step
              number={4}
              title="Review quarterly reports"
              description="For each reporting cycle, run grantee reports through the quarterly template. DOCex flags gaps, financial/service inconsistencies, and drafts the follow-up email."
              icon={<ScrollText className="h-5 w-5" />}
              href="/app?template=quarterly-report-review"
              cta="Open quarterly review"
              count={null}
              countLabel=""
            />

            <Step
              number={5}
              title="Follow up on gaps"
              description="DOCex auto-drafts polite follow-up notes whenever an applicant or grantee has missing items. Edit before sending."
              icon={<Mail className="h-5 w-5" />}
              href="/app"
              cta="In Extraction results"
              count={null}
              countLabel=""
              muted
            />
          </div>

          {/* Dashboard widgets */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              At a glance
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <Widget
                label="Rulebooks"
                count={rulebookCount}
                href="/compliance"
                icon={<ClipboardCheck className="h-4 w-4 text-brand-600" />}
                hint="Policies interpreted, ready to check disbursements against"
              />
              <Widget
                label="Verifications run"
                count={verifyCount}
                href="/verify"
                icon={<Landmark className="h-4 w-4 text-brand-600" />}
                hint="Every bank batch ever run, all purposes"
              />
              <Widget
                label="Approved PVs"
                count={checkApprovedCount}
                href="/compliance/checks"
                icon={<Users className="h-4 w-4 text-brand-600" />}
                hint="Compliance-cleared payment vouchers, audit-ready"
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

/* ─── Step row ─────────────────────────────────────────────────────────── */

function Step({
  number,
  title,
  description,
  icon,
  href,
  cta,
  count,
  countLabel,
  muted,
}: {
  number: number;
  title: string;
  description: string;
  icon: React.ReactNode;
  href: string | null;
  cta: string;
  count: number | null;
  countLabel: string;
  muted?: boolean;
}) {
  const content = (
    <div
      className={`group flex items-start gap-4 rounded-xl border p-5 transition ${
        href
          ? "border-gray-200 bg-white hover:border-brand-300 hover:shadow-card-hover"
          : "border-gray-100 bg-gray-50/60"
      } ${muted ? "opacity-80" : ""}`}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <span className="text-sm font-bold">{number}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-gray-500">{icon}</span>
          <h3
            className={`text-base font-semibold ${
              href ? "text-gray-900 group-hover:text-brand-700" : "text-gray-700"
            }`}
          >
            {title}
          </h3>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-gray-600">
          {description}
        </p>
        {count !== null && (
          <p className="mt-2 text-xs font-medium text-gray-500">
            <span className="tabular-nums text-gray-900">{count}</span>{" "}
            {countLabel}
          </p>
        )}
      </div>
      {href && (
        <div className="flex shrink-0 items-center gap-1.5 text-sm font-medium text-brand-600 group-hover:text-brand-700">
          {cta}
          <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
        </div>
      )}
      {!href && (
        <span className="shrink-0 text-xs italic text-gray-400">{cta}</span>
      )}
    </div>
  );

  return href ? <Link href={href}>{content}</Link> : content;
}

/* ─── Dashboard widget ─────────────────────────────────────────────────── */

function Widget({
  label,
  count,
  href,
  icon,
  hint,
}: {
  label: string;
  count: number | null;
  href: string;
  icon: React.ReactNode;
  hint: string;
}) {
  return (
    <Link
      href={href}
      className="group block rounded-xl border border-gray-200 bg-white p-4 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-600">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-3xl font-bold tabular-nums text-gray-900 transition-colors group-hover:text-brand-700">
        {count === null ? (
          <Loader2 className="h-6 w-6 animate-spin text-gray-300" />
        ) : (
          count
        )}
      </p>
      <p className="mt-1 text-[11px] text-gray-500">{hint}</p>
    </Link>
  );
}
