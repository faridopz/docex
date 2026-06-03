"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileSpreadsheet,
  Landmark,
  LayoutGrid,
  type LucideIcon,
  Mail,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * /tour — the immersive, role-based intro to ALL of DOCex.
 *
 * Replaces the old "Tour the Co-Pilots" link that dumped everyone onto the
 * sub-award page. Built on first-run onboarding fundamentals:
 *   - Role/use-case entry (personalisation lifts activation 30–50%)
 *   - One flow at a time (working memory holds ~4 items — progressive
 *     disclosure cuts overload and raises completion)
 *   - Learn-by-doing: every flow ends in a real "Try it" CTA, not a wall
 *     of text
 *   - Always skippable; always one clear next action
 *
 * Content is deliberately accurate to what each engine actually does
 * (screener.py, attendance_agent.py, compliance.py, knowledge.py,
 * bank_verify.py) so the tour never over-promises.
 */

type FlowId = "screening" | "attendance" | "compliance" | "knowledge";

type Step = { title: string; detail: string };

type Flow = {
  id: FlowId;
  icon: LucideIcon;
  name: string;
  audience: string;
  problem: string;
  steps: Step[];
  outcome: string;
  ctaLabel: string;
  ctaHref: string;
};

const FLOWS: Flow[] = [
  {
    id: "screening",
    icon: Users,
    name: "Screen & analyse documents",
    audience: "Sub-award & grants teams",
    problem:
      "Hundreds of partner applications, each with 5–8 documents, all read by hand to answer the same standard questions.",
    steps: [
      {
        title: "Define your questions in plain language",
        detail:
          "“Is this org registered with CAC?” · “What states do they work in?” · “Have they managed donor funds before?” No templates to configure.",
      },
      {
        title: "Upload each applicant's documents",
        detail:
          "Registration certificate, proposal, audit report, financials — drop them in together, one applicant at a time or in a batch.",
      },
      {
        title: "DOCex reads everything and answers",
        detail:
          "Every question gets an answer, the source document, the exact quote, and a confidence level — found, inferred, or not found.",
      },
      {
        title: "Export the table to Excel",
        detail:
          "One row per applicant, one column per question. The team lives in Excel — so the answer lands where they already work.",
      },
    ],
    outcome: "Two-week screening cycles compressed to an afternoon.",
    ctaLabel: "Try screening",
    ctaHref: "/app?template=sub-award-screening",
  },
  {
    id: "attendance",
    icon: FileSpreadsheet,
    name: "Attendance to paid",
    audience: "Events, training & programs teams",
    problem:
      "Cross-referencing an attendance log against a payment list by hand, multiplying days × rate, then thumb-typing every account number into a bank app.",
    steps: [
      {
        title: "Drop in two files",
        detail:
          "The attendance log (who showed up each day) and the payment info form (who's registered, plus their bank details).",
      },
      {
        title: "DOCex matches names across both",
        detail:
          "Fuzzy-matching buckets everyone automatically: paid, no attendance record, or no payment info — so nobody slips through.",
      },
      {
        title: "It calculates days × rate",
        detail:
          "Per-diem rates applied from your rate card, days counted from the log, totals built per person.",
      },
      {
        title: "Every bank account is verified",
        detail:
          "Each account is checked against the bank-of-record holder before the schedule ever reaches finance.",
      },
    ],
    outcome: "Three hours of cross-checking becomes a three-minute review.",
    ctaLabel: "Try attendance & payment",
    ctaHref: "/agents/attendance-payment",
  },
  {
    id: "compliance",
    icon: ShieldCheck,
    name: "Compliance & approvals",
    audience: "Compliance & finance teams",
    problem:
      "Checking each payment voucher against policy by memory, then chasing approvals through endless Outlook threads with no audit trail.",
    steps: [
      {
        title: "Upload your policy once",
        detail:
          "Procurement, travel, or donor policy — DOCex turns it into an editable rulebook you can reuse on every payment.",
      },
      {
        title: "Every voucher is checked rule by rule",
        detail:
          "Each rule gets a verdict with citations from both the policy and the voucher — defensible, not a black box.",
      },
      {
        title: "Escalate or ask a question — in one thread",
        detail:
          "DOCex emails the right person a one-click link to the check. The question, the answer, and the audit trail stay together — no 30-email chain.",
      },
      {
        title: "Approve with a frozen audit trail",
        detail:
          "Every decision, escalation, and signature is timestamped. Edit the policy a year later and yesterday's audit doesn't change underneath you.",
      },
    ],
    outcome: "Defensible compliance and approvals, with no extra paperwork.",
    ctaLabel: "Try compliance",
    ctaHref: "/compliance",
  },
  {
    id: "knowledge",
    icon: BookOpen,
    name: "Ask your document library",
    audience: "Anyone with a document library",
    problem:
      "The answer is in a board deck or project report somewhere — but finding it means opening twenty files.",
    steps: [
      {
        title: "Upload your decks and reports",
        detail:
          "Board decks, training slides, project reports — DOCex reads every page into one searchable library.",
      },
      {
        title: "Ask the whole library a question",
        detail:
          "“What were last quarter's flagged risks?” Ask in plain language across everything you've uploaded.",
      },
      {
        title: "Every answer is cited",
        detail:
          "Answers come back with clickable citations pointing to the exact slide or page — so you can verify against the source, never guess.",
      },
    ],
    outcome: "“What did we flag last quarter?” — answered in seconds, with sources.",
    ctaLabel: "Try the knowledge hub",
    ctaHref: "/knowledge",
  },
];

export default function TourPage() {
  const [activeId, setActiveId] = useState<FlowId | null>(null);
  const active = FLOWS.find((f) => f.id === activeId) ?? null;

  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7] text-gray-900">
      {/* Minimal header — home + skip */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 transition hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <Link
            href="/app"
            className="text-sm font-medium text-gray-500 underline-offset-4 transition hover:text-gray-900 hover:underline"
          >
            Skip the tour →
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-12">
        {/* Intro */}
        <div className="max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600 shadow-sm">
            <Sparkles className="h-3 w-3 text-brand-600" />
            A 3-minute tour
          </span>
          <h1 className="mt-6 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            What do you spend your week on?
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-gray-600">
            DOCex replaces the document-heavy parts of four different roles.
            Pick the one closest to yours and we'll walk you through exactly
            how it works — then you can try it on sample data.
          </p>
        </div>

        {/* Role picker */}
        <div className="mt-10 grid gap-3 sm:grid-cols-2">
          {FLOWS.map((f) => {
            const selected = f.id === activeId;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setActiveId(f.id)}
                aria-pressed={selected}
                className={cn(
                  "group flex items-start gap-4 rounded-2xl border bg-white p-5 text-left transition",
                  selected
                    ? "border-brand-300 shadow-card-hover ring-2 ring-brand-100"
                    : "border-gray-200 hover:border-brand-200 hover:shadow-card-hover",
                )}
              >
                <div
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ring-1 transition",
                    selected
                      ? "bg-brand-600 text-white ring-brand-600"
                      : "bg-amber-50 text-amber-700 ring-amber-100",
                  )}
                >
                  <f.icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-medium uppercase tracking-widest text-gray-400">
                    {f.audience}
                  </p>
                  <h3 className="mt-0.5 text-base font-semibold text-gray-900 group-hover:text-brand-700">
                    {f.name}
                  </h3>
                </div>
              </button>
            );
          })}
        </div>

        {/* Walkthrough for the selected flow */}
        {active && (
          <section className="mt-10 overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-card">
            <div className="border-b border-gray-100 bg-gradient-to-br from-brand-50/40 via-white to-amber-50/20 px-7 py-6">
              <p className="text-xs font-semibold uppercase tracking-widest text-brand-700">
                {active.audience}
              </p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight text-gray-900">
                {active.name}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">
                <span className="font-medium text-gray-700">The pain today:</span>{" "}
                {active.problem}
              </p>
            </div>

            <ol className="divide-y divide-gray-100">
              {active.steps.map((s, i) => (
                <li key={i} className="flex items-start gap-4 px-7 py-5">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50 text-sm font-bold text-brand-600">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-900">
                      {s.title}
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-gray-600">
                      {s.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="flex flex-col gap-4 border-t border-gray-100 bg-gray-50/50 px-7 py-6 sm:flex-row sm:items-center sm:justify-between">
              <p className="inline-flex items-center gap-2 text-sm font-medium text-brand-700">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                {active.outcome}
              </p>
              <Link
                href={active.ctaHref}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-brand-600 px-6 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              >
                {active.ctaLabel}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </section>
        )}

        {/* Footer cue */}
        <div className="mt-10 flex items-center justify-between rounded-2xl border border-gray-200 bg-white px-6 py-5">
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <LayoutGrid className="h-4 w-4 text-brand-600" />
            {active
              ? "Want to see another? Pick a different role above."
              : "Pick a role above to see how it works."}
          </div>
          <Link
            href="/app"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 underline-offset-4 transition hover:text-gray-900 hover:underline"
          >
            <Mail className="h-3.5 w-3.5" />
            Or just start with sample data
          </Link>
        </div>
      </main>
    </div>
  );
}
