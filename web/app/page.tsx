import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Landmark,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Landing page — reframed June 2026.
 *
 * Goals of this rewrite:
 *   1. Global, cohesive product framing. No country-specific copy
 *      anywhere on the page. The product happens to test first against
 *      African NGO workflows, but the primitives generalise — say so.
 *   2. One sentence per section that a finance lead anywhere in the
 *      world reads and gets immediately: "verify payments, check
 *      compliance, read every document, in minutes."
 *   3. Anonymised examples in the Assistant card (no real personal
 *      names) — looks more credible to a CTO doing diligence and
 *      respects everyone's identity.
 *   4. Trust section reframed around outcomes ("audit trail you can
 *      defend") not infrastructure ("Paystack") — Paystack is an
 *      implementation detail, the buyer cares about defensibility.
 *
 * Design language: warm cream `#fafaf7`, generous whitespace, single
 * subtle gradient at the hero, opinionated big type. Reference doc:
 * `UI_DIRECTION.md` at the repo root.
 */

// Three Co-Pilots = three roles we replace. Each card answers "what is
// this for someone like me?" without naming a country or person.
const copilots = [
  {
    icon: Users,
    name: "Sub-award Co-Pilot",
    audience: "for sub-award & grants teams",
    pitch:
      "Screen hundreds of partner applications in an afternoon. Verify grantee accounts before disbursement. Review quarterly reports against the original proposal. The document-heavy parts of a sub-award officer's week, done by lunchtime.",
    proof: "Two-week screening cycles compressed to an afternoon.",
    href: "/agents/sub-award",
  },
  {
    icon: Landmark,
    name: "Attendance & Payment Flow",
    audience: "for events, training & programs teams",
    pitch:
      "Drop in your attendance log and your payment list. The flow matches names, applies per-diem rates, surfaces attendees who never made it onto the payment schedule, and verifies every bank account before the schedule hits finance. Save attendance lists to reuse repeat attendees next time.",
    proof: "Three hours of cross-checking becomes a three-minute review.",
    href: "/agents/attendance-payment",
  },
  {
    icon: ShieldCheck,
    name: "Compliance Co-Pilot",
    audience: "for compliance & finance teams",
    pitch:
      "Upload your procurement, travel, or donor policy once. The Co-Pilot turns it into an editable rulebook. Every payment voucher gets checked rule by rule, with citations from both the policy and the voucher — and an audit trail that survives later edits.",
    proof: "Defensible compliance, every time, with no extra paperwork.",
    href: "/compliance",
  },
  {
    icon: BookOpen,
    name: "Knowledge Hub",
    audience: "for anyone with a document library",
    pitch:
      "Upload your board decks, training slides, project reports. The Hub reads every page and lets your team chat with the whole library — every answer comes back with citations you can click to verify against the source document.",
    proof: "\"What were last quarter's flagged risks?\" — answered in five seconds, with sources.",
    href: "/knowledge",
  },
];

// Trust pillars — outcomes, not infrastructure. A buyer cares about
// "can I defend this to my auditor", not "what payment provider do you
// use under the hood".
const trust = [
  {
    label: "Verified payments, every time",
    detail:
      "Recipient names matched to bank-of-record holders before money moves. No more thumb-typing account numbers into a phone app and hoping.",
  },
  {
    label: "Audit trail that doesn't drift",
    detail:
      "Every check, verdict, approval, escalation, and signature is timestamped and frozen. Edit a policy a year later and yesterday's audit doesn't quietly change underneath you.",
  },
  {
    label: "Reads the documents you already have",
    detail:
      "PDFs, Word docs, Excel sheets, scanned scans, slide decks. No new template to roll out. No spreadsheet macros to maintain. Whatever your team collects today, DOCex reads it tomorrow.",
  },
  {
    label: "Briefed in plain English, not just processed",
    detail:
      "Every result comes with a plain-English brief — what happened, what matters, what to do next. Tables and citations are there if you want them. Most days, you won't need to scroll.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7] text-gray-900">
      {/* Nav — minimal */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link
            href="/"
            className="text-xl font-bold tracking-tight text-gray-900"
          >
            DOCex
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/agents/sub-award"
              className="hidden text-sm font-medium text-gray-600 transition hover:text-gray-900 sm:inline"
            >
              Co-Pilots
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
          {/* Warm gradient backdrop — barely there, but reframes the whole
              feel from "tool" to "considered". */}
          <div
            aria-hidden
            className="absolute inset-0 -z-10 bg-gradient-to-br from-amber-50/60 via-[#fafaf7] to-violet-50/40"
          />
          <div className="mx-auto max-w-5xl px-6 pt-32 pb-24 text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-medium text-gray-600 shadow-sm">
              <Sparkles className="h-3 w-3 text-brand-600" />
              The AI back-office for document-heavy operations
            </div>

            <h1 className="mt-8 text-5xl font-semibold leading-[1.05] tracking-tight text-gray-900 sm:text-6xl md:text-7xl">
              Verify payments. Check compliance.
              <br />
              <span className="text-brand-600">Read every document.</span>{" "}
              <span className="text-gray-500">In minutes.</span>
            </h1>

            <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-gray-600 sm:text-xl">
              DOCex is the cohesive AI back-office for finance, programs,
              sub-award, and compliance teams. Three Co-Pilots, four
              primitives, one audit trail. Built so the document-heavy parts
              of your week take an afternoon, not two.
            </p>

            <div className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/app">
                <Button size="lg" className="gap-2 rounded-full px-7 shadow-sm">
                  Try DOCex free
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link
                href="/compliance"
                className="text-sm font-medium text-gray-600 underline-offset-4 transition hover:text-gray-900 hover:underline"
              >
                See it on a real compliance check →
              </Link>
            </div>
            <p className="mt-5 text-xs text-gray-400">
              No card required · Start with sample data · Bring your own
              when you're ready
            </p>
          </div>
        </section>

        {/* ─── Co-Pilots ────────────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-20 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                Co-Pilots, not chatbots
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Built for the work that costs you weeks.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                DOCex isn't a chatbot you ask questions to. It's three named
                Co-Pilots — each one replacing the document-heavy parts of a
                specific role on your team. They share an engine, an audit
                trail, and a single price.
              </p>
            </div>

            <div className="space-y-4">
              {copilots.map((a) => (
                <Link
                  key={a.name}
                  href={a.href}
                  className="group flex flex-col gap-6 rounded-3xl border border-gray-200 bg-white p-8 transition hover:border-brand-200 hover:shadow-card-hover sm:flex-row sm:items-center sm:gap-10 sm:p-10"
                >
                  <div className="flex shrink-0 items-start gap-5 sm:w-72">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                      <a.icon className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-widest text-gray-400">
                        {a.audience}
                      </p>
                      <h3 className="mt-1 text-xl font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
                        {a.name}
                      </h3>
                    </div>
                  </div>
                  <div className="flex-1">
                    <p className="text-base leading-relaxed text-gray-700">
                      {a.pitch}
                    </p>
                    <p className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-brand-700">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      {a.proof}
                    </p>
                  </div>
                  <ArrowRight className="hidden h-5 w-5 shrink-0 text-gray-300 transition group-hover:translate-x-1 group-hover:text-brand-600 sm:block" />
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* ─── The Assistant ────────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-[#fafaf7]">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="grid items-center gap-16 lg:grid-cols-2">
              <div>
                <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                  The Assistant
                </p>
                <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                  A brief, not just a result.
                </h2>
                <p className="mt-5 text-lg leading-relaxed text-gray-600">
                  Every time a Co-Pilot finishes a run, you get a
                  plain-English brief. What happened. What matters. What to
                  do next. The verdict table is still there — but you don't
                  have to read it first.
                </p>
                <p className="mt-4 text-sm text-gray-500">
                  No dashboards to learn. No spreadsheets to interpret.
                  Just a colleague who reads everything for you and tells
                  you what to do.
                </p>
              </div>

              {/* Anonymised Assistant brief example. Visual language
                  matches /components/AssistantBrief.tsx so a prospect
                  recognises the pattern when they open the product. */}
              <div className="overflow-hidden rounded-3xl border border-brand-100 bg-gradient-to-br from-brand-50/30 via-white to-violet-50/20 p-6 shadow-card sm:p-8">
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold uppercase tracking-widest text-brand-700">
                      DOCex Assistant
                    </p>
                    <p className="mt-3 text-base font-semibold leading-snug text-gray-900">
                      4 of 5 payments cleared. One blocker.
                    </p>
                    <p className="mt-2 text-sm leading-relaxed text-gray-700">
                      Recipient A matched 100% — release. Recipient B is a
                      likely typo of the same holder; safe to release once
                      programs confirms. Recipient C has a completely
                      different name on file from the one on the schedule —
                      block pending review.
                    </p>
                    <div className="mt-5 space-y-1.5">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
                        Suggested next steps
                      </p>
                      <div className="flex flex-wrap gap-2 pt-1">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                          Block Recipient C
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                          Confirm Recipient B with programs
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-700 ring-1 ring-gray-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
                          Release the rest
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Trust / outcomes ─────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-16 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                Built around the work
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Designed for how the work actually happens.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                Not retrofitted from a generic grant-management tool. Built
                around the document flows your team already runs —
                spreadsheets, scanned vouchers, attendance sheets, donor
                policies, board decks. Whatever you have, DOCex reads.
              </p>
            </div>

            <div className="grid gap-8 sm:grid-cols-2">
              {trust.map((t) => (
                <div
                  key={t.label}
                  className="rounded-2xl border border-gray-200 bg-[#fafaf7] p-7"
                >
                  <p className="text-base font-semibold text-gray-900">
                    {t.label}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">
                    {t.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Closing CTA ──────────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-[#fafaf7]">
          <div className="mx-auto max-w-3xl px-6 py-32 text-center">
            <h2 className="text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
              The back-office, done.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-gray-600">
              Spin up the Co-Pilots you need. Run them on sample data first.
              Bring your own files when you're ready. See what a week of work
              feels like in three minutes.
            </p>
            <div className="mt-12 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Link href="/app">
                <Button size="lg" className="gap-2 rounded-full px-7 shadow-sm">
                  Try DOCex free
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link
                href="/agents/sub-award"
                className="text-sm font-medium text-gray-600 underline-offset-4 transition hover:text-gray-900 hover:underline"
              >
                Tour the Co-Pilots →
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer — minimal, calm */}
      <footer className="border-t border-gray-100 bg-[#fafaf7] py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-gray-400 sm:flex-row">
          <p>DOCex · The AI back-office for document-heavy operations</p>
          <p>© 2026 DOCex</p>
        </div>
      </footer>
    </div>
  );
}
