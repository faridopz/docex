import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileSearch,
  Landmark,
  Layers,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Landing page — rebuilt June 2026 to match what the product actually does.
 *
 * Positioning (per founder direction): lead with the compliance & approvals
 * OS, on top of an honest document-intelligence engine. Capability-led, not
 * role-led — "Sub-award" etc. are use-cases of the capabilities, not the
 * headline. Every claim here maps to real behaviour in the codebase:
 *   - compliance.py / api/compliance_routes.py — rulebooks, per-rule verdicts
 *     with citations, payment-first checks, escalation, frozen audit trail
 *   - notifications.py — escalation/clarification emails (Outlook/Gmail SMTP)
 *   - screener.py — answers with source doc, exact quote, confidence
 *   - lib/template-store.ts — reusable question templates
 *   - attendance_agent.py — match, per-diem, bank verify
 *   - knowledge.py — cited Q&A over a document library
 *   - bank_verify.py — recipient name vs bank-of-record holder
 */

// Capability pillars — what the product can do, each mapping to a real flow.
const capabilities: {
  icon: LucideIcon;
  name: string;
  blurb: string;
  href: string;
}[] = [
  {
    icon: ShieldCheck,
    name: "Compliance & approvals",
    blurb:
      "Turn a policy into a reusable rulebook. Check any invoice against one or more policy sets, escalate without the email chain, approve with an audit trail that holds up later.",
    href: "/compliance",
  },
  {
    icon: FileSearch,
    name: "Document extraction",
    blurb:
      "Ask plain-language questions across a stack of documents. Every answer comes back with the source document, the exact quote, and a confidence level.",
    href: "/app",
  },
  {
    icon: Layers,
    name: "Reusable templates",
    blurb:
      "Save the questions your team asks every time — application reviews, invoice fields, report reconciliations — and run them on every new batch.",
    href: "/templates",
  },
  {
    icon: Landmark,
    name: "Attendance & payment",
    blurb:
      "Match an attendance log against a payment list, apply per-diem rates, and verify every bank account before the schedule reaches finance.",
    href: "/agents/attendance-payment",
  },
  {
    icon: BookOpen,
    name: "Knowledge Q&A",
    blurb:
      "Ask your library of decks and reports a question and get an answer with clickable citations pointing to the exact slide or page.",
    href: "/knowledge",
  },
  {
    icon: CheckCircle2,
    name: "Bank verification",
    blurb:
      "Confirm a recipient's name matches the bank-of-record account holder before money moves — one account or a whole schedule.",
    href: "/verify",
  },
];

// The payment lifecycle — the compliance/approvals story, step by step.
const lifecycle: { n: number; title: string; detail: string }[] = [
  {
    n: 1,
    title: "Turn your policy into a rulebook",
    detail:
      "Upload your procurement, travel, or donor policy — one document or several. DOCex reads it and extracts every testable rule into a reusable policy set you can edit.",
  },
  {
    n: 2,
    title: "Check a payment against it",
    detail:
      "Drop in the invoice or voucher and pick which policy set(s) it has to satisfy. Every rule gets a verdict, with citations from both the policy and the payment.",
  },
  {
    n: 3,
    title: "Resolve questions in one thread",
    detail:
      "Escalate to a reviewer or ask the vendor a question — DOCex emails them a one-click link back to the check. The question, the answer, and the trail stay together.",
  },
  {
    n: 4,
    title: "Approve with a defensible trail",
    detail:
      "Every check, verdict, escalation, and signature is timestamped and frozen. Edit the policy a year later and yesterday's audit doesn't change underneath you.",
  },
];

const differentiators: { label: string; detail: string }[] = [
  {
    label: "Cited, not just confident",
    detail:
      "Every answer and verdict points back to the source — the exact quote, the page, the rule. Nothing to take on faith, which is the whole point when an auditor asks why.",
  },
  {
    label: "Repeatable, not one-off",
    detail:
      "Save a template or a policy set once and run it across 200 documents the same way every time. A chat prompt can't give a team that consistency.",
  },
  {
    label: "Structured for the work",
    detail:
      "One row per applicant in Excel, per-rule compliance verdicts, side-by-side document comparisons that cite both sources. Outputs that drop into how you already work.",
  },
  {
    label: "An audit trail that doesn't drift",
    detail:
      "Decisions, approvals, escalations, and signatures are timestamped and frozen against a snapshot of the rules at check time. Defensible months later.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7] text-gray-900">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="text-xl font-bold tracking-tight text-gray-900">
            DOCex
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/tour"
              className="hidden text-sm font-medium text-gray-600 transition hover:text-gray-900 sm:inline"
            >
              Tour
            </Link>
            <Link
              href="/compliance"
              className="hidden text-sm font-medium text-gray-600 transition hover:text-gray-900 sm:inline"
            >
              Compliance
            </Link>
            <Link href="/app">
              <Button size="sm" className="rounded-full">
                Try DOCex
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* ─── Hero ─────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          <div
            aria-hidden
            className="absolute inset-0 -z-10 bg-gradient-to-br from-amber-50/60 via-[#fafaf7] to-violet-50/40"
          />
          <div className="mx-auto max-w-5xl px-6 pt-32 pb-24 text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-medium text-gray-600 shadow-sm">
              <Sparkles className="h-3 w-3 text-brand-600" />
              Compliance, approvals & document intelligence for NGOs
            </div>

            <h1 className="mt-8 text-5xl font-semibold leading-[1.05] tracking-tight text-gray-900 sm:text-6xl md:text-7xl">
              The operating system for
              <br />
              <span className="text-brand-600">payment approvals</span>{" "}
              <span className="text-gray-500">and compliance.</span>
            </h1>

            <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-gray-600 sm:text-xl">
              Check every payment against your own policies, resolve questions
              without the endless Outlook chain, and keep an audit trail you
              can defend — powered by an engine that reads any stack of
              documents and answers with the source, the quote, and a
              confidence level.
            </p>

            <div className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/compliance/check">
                <Button size="lg" className="gap-2 rounded-full px-7 shadow-sm">
                  Check a payment
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link
                href="/tour"
                className="text-sm font-medium text-gray-600 underline-offset-4 transition hover:text-gray-900 hover:underline"
              >
                Take the 3-minute tour →
              </Link>
            </div>
            <p className="mt-5 text-xs text-gray-400">
              No card required · Start with sample data · Bring your own when
              you're ready
            </p>
          </div>
        </section>

        {/* ─── Payment lifecycle ────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-16 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                From voucher to approved
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Every payment, checked and accounted for.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                The real pain isn't the rule — it's the chasing, the missing
                document, the thread with everyone CC'd, and no record of who
                decided what. DOCex turns that into one clean path.
              </p>
            </div>

            <div className="grid gap-6 sm:grid-cols-2">
              {lifecycle.map((s) => (
                <div
                  key={s.n}
                  className="flex items-start gap-5 rounded-2xl border border-gray-200 bg-[#fafaf7] p-7"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
                    {s.n}
                  </span>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">
                      {s.title}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-gray-600">
                      {s.detail}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-10">
              <Link
                href="/compliance/check"
                className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 underline-offset-4 hover:underline"
              >
                <ShieldCheck className="h-4 w-4" />
                See it on a payment check
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* ─── The engine underneath ───────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-[#fafaf7]">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="grid items-center gap-16 lg:grid-cols-2">
              <div>
                <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                  The engine underneath
                </p>
                <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                  What a chatbot can't do.
                </h2>
                <p className="mt-5 text-lg leading-relaxed text-gray-600">
                  Compliance is one thing DOCex does with a deeper capability:
                  reading documents and answering specific questions, with
                  proof. Ask anything across a stack of files and get the
                  answer, the source document, the exact quote, and whether it
                  was found, inferred, or not present.
                </p>
                <p className="mt-4 text-sm leading-relaxed text-gray-500">
                  Save those questions as a template and run them across two
                  hundred applications the same way every time. Compare two
                  documents that should agree — a financial report against a
                  service report — and DOCex cites both sides of every
                  mismatch. Then it exports one clean row per document to
                  Excel.
                </p>
                <Link
                  href="/templates"
                  className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-brand-700 underline-offset-4 hover:underline"
                >
                  <Layers className="h-4 w-4" />
                  Browse the template library
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>

              {/* Extraction-answer example — mirrors the real result shape. */}
              <div className="space-y-3">
                <AnswerCard
                  q="Is this organisation registered with CAC?"
                  a="Yes — CAC registration RC 1043221, issued 14 March 2019."
                  source="registration-cert.pdf"
                  confidence="found"
                />
                <AnswerCard
                  q="Has the org managed donor funds before?"
                  a="Likely — references a 2023 Gates-funded TB project, though no grant agreement is attached."
                  source="org-profile.pdf"
                  confidence="inferred"
                />
                <AnswerCard
                  q="Does the org have an anti-fraud policy?"
                  a="Not mentioned in any of the documents provided."
                  source="—"
                  confidence="not_found"
                />
              </div>
            </div>
          </div>
        </section>

        {/* ─── Capabilities ─────────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-16 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                One platform
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Everything the document-heavy work needs.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                Six capabilities, one engine, one audit trail. Use the one you
                need today; the rest are there when you're ready.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {capabilities.map((c) => (
                <Link
                  key={c.name}
                  href={c.href}
                  className="group flex flex-col gap-4 rounded-2xl border border-gray-200 bg-white p-6 transition hover:border-brand-200 hover:shadow-card-hover"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                    <c.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
                      {c.name}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-gray-600">
                      {c.blurb}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Why it's different ───────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-[#fafaf7]">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-16 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                Why it holds up
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Built to be defended, not just trusted.
              </h2>
            </div>

            <div className="grid gap-8 sm:grid-cols-2">
              {differentiators.map((d) => (
                <div
                  key={d.label}
                  className="rounded-2xl border border-gray-200 bg-white p-7"
                >
                  <p className="text-base font-semibold text-gray-900">
                    {d.label}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">
                    {d.detail}
                  </p>
                </div>
              ))}
            </div>

            {/* Brief callout */}
            <div className="mt-12 flex items-start gap-4 rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50/40 via-white to-violet-50/20 p-7">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-base font-semibold text-gray-900">
                  And a plain-English brief on every run.
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-gray-600">
                  After each check or extraction, DOCex writes a short brief —
                  what happened, what matters, what to do next. The tables and
                  citations are right there; most days you won't need to scroll.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Closing CTA ──────────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-3xl px-6 py-32 text-center">
            <h2 className="text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
              See a week of work in three minutes.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-gray-600">
              Run a payment check or an extraction on sample data first. Bring
              your own policies and documents when you're ready.
            </p>
            <div className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/compliance/check">
                <Button size="lg" className="gap-2 rounded-full px-7 shadow-sm">
                  Check a payment
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link
                href="/tour"
                className="text-sm font-medium text-gray-600 underline-offset-4 transition hover:text-gray-900 hover:underline"
              >
                Take the tour →
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-100 bg-[#fafaf7] py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-gray-400 sm:flex-row">
          <p>DOCex · Compliance, approvals & document intelligence</p>
          <p>© 2026 DOCex</p>
        </div>
      </footer>
    </div>
  );
}

/* ─── Extraction answer example card ──────────────────────────────────── */

const CONFIDENCE: Record<
  "found" | "inferred" | "not_found",
  { label: string; cls: string; dot: string }
> = {
  found: {
    label: "Found",
    cls: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
  inferred: {
    label: "Inferred",
    cls: "bg-amber-50 text-amber-700 ring-amber-200",
    dot: "bg-amber-400",
  },
  not_found: {
    label: "Not found",
    cls: "bg-gray-100 text-gray-600 ring-gray-200",
    dot: "bg-gray-400",
  },
};

function AnswerCard({
  q,
  a,
  source,
  confidence,
}: {
  q: string;
  a: string;
  source: string;
  confidence: "found" | "inferred" | "not_found";
}) {
  const c = CONFIDENCE[confidence];
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-card">
      <p className="text-sm font-semibold text-gray-900">{q}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-gray-700">{a}</p>
      <div className="mt-3 flex items-center gap-2 text-[11px]">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-medium ring-1 ${c.cls}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
          {c.label}
        </span>
        <span className="inline-flex items-center gap-1 text-gray-400">
          <FileSearch className="h-3 w-3" />
          {source}
        </span>
      </div>
    </div>
  );
}
