"use client";

import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  FileSearch,
  Mail,
  ScrollText,
} from "lucide-react";
import { AppNav } from "@/components/AppNav";
import { GuidanceCard } from "@/components/GuidanceCard";

/**
 * /agents/sub-award — the sub-award screening workflow as one branded shell.
 *
 * The Sub-award Co-Pilot is a *lifecycle shell* over DOCex's extraction
 * primitive. It is screening + deep document analysis only — grantee
 * payment/bank verification is NOT part of the sub-award process (that
 * lives in the Attendance & Payment Flow and the standalone Bank Verify
 * check).
 *
 *   1. Screen applicants          → Extraction (sub-award template)
 *   2. Award decision             → human-only step (we surface, not decide)
 *   3. Review quarterly reports   → Extraction (quarterly review template)
 *   4. Follow up on gaps          → existing draft-followups flow
 *
 * Each step links into the primitive pre-filled with the right template
 * so the user doesn't have to remember which settings to pick.
 */

export default function SubAwardAgentPage() {
  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <AppNav active="sub-award">
        <Link
          href="/app?template=sub-award-screening"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          Open screening
        </Link>
      </AppNav>

      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="space-y-8">
          {/* Hero */}
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Sub-award Co-Pilot
            </h1>
            <p className="mt-2 max-w-2xl text-base text-gray-600">
              Screening and deep document analysis for partner applications,
              in one place — from initial application screening through
              quarterly report review. Each step uses DOCex's extraction
              engine, pre-configured for sub-award work.
            </p>
          </div>

          <GuidanceCard title="How this works">
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
              title="Review quarterly reports"
              description="For each reporting cycle, run grantee reports through the quarterly template. DOCex flags gaps, financial/service inconsistencies, and drafts the follow-up email."
              icon={<ScrollText className="h-5 w-5" />}
              href="/app?template=quarterly-report-review"
              cta="Open quarterly review"
              count={null}
              countLabel=""
            />

            <Step
              number={4}
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
