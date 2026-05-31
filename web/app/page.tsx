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
 * Landing page — rebuilt May 2026 to reflect DOCex as an agentic platform
 * rather than a single-purpose extraction tool. Design language inspired
 * by Anthropic's homepage: calm, generous whitespace, fewer sections each
 * doing more work, clear "what is this for me" framing.
 *
 * Design choices that matter:
 *   - Cream/warm background instead of pure white. Softer feel.
 *   - Big serif-ish hero (using font-serif via tracking, kept system font
 *     to avoid adding a new font dep). Anthropic uses Tiempos; we use a
 *     tighter Geist with serif-like weight contrast.
 *   - Three agents are the primary frame, not "any documents". Specificity
 *     beats versatility on a first impression.
 *   - The Assistant briefing screenshot-style card is the hero of section 3
 *     — show, don't just tell.
 *   - One primary CTA, one secondary. Not five.
 *   - py-32 between major sections (vs the old py-20). Breathing room.
 */

// Three agents = three jobs. Each card answers "what is this for me?"
const agents = [
  {
    icon: Users,
    name: "Sub-award Agent",
    audience: "for sub-award teams",
    pitch:
      "Screen 200 applications in an afternoon. Verify grantee bank accounts before disbursement. Review quarterly reports. Everything an officer like Abosede does, made fast.",
    proof: "Screening that took two weeks now finishes by lunchtime.",
    href: "/agents/sub-award",
  },
  {
    icon: Landmark,
    name: "Programs Agent",
    audience: "for events & training teams",
    pitch:
      "Drop in your attendance log and your payment info form. DOCex matches names, applies your per-diem rates, surfaces who attended without showing up on the bank list, and verifies every account before the schedule reaches finance.",
    proof: "Three hours of cross-checking becomes a three-minute review.",
    href: "/agents/attendance-payment",
  },
  {
    icon: ShieldCheck,
    name: "Compliance Agent",
    audience: "for compliance officers",
    pitch:
      "Upload your procurement policy once. DOCex turns it into an editable rulebook. Every payment voucher gets checked rule by rule, with citations from both sides and an audit trail that survives policy edits.",
    proof: "Defensible compliance, every time, with no extra paperwork.",
    href: "/compliance",
  },
  {
    icon: BookOpen,
    name: "Knowledge Hub",
    audience: "for anyone who reads slides",
    pitch:
      "Upload your check-in decks, board presentations, training slides. DOCex reads every slide and lets you chat with the whole library — answers come back with [Slide N] citations you can click to verify against the source.",
    proof: "Ask 'which states are below 50% on PPH?' — get the answer in 5 seconds, with citations.",
    href: "/knowledge",
  },
];

// Trust pillars — the "this is real" credibility section. Subtle, not loud.
const trust = [
  {
    label: "African banks, live",
    detail:
      "Paystack-powered bank-of-record verification for every recipient. No more thumb-typing account numbers into a phone app.",
  },
  {
    label: "Audit trail, automatic",
    detail:
      "Every check, every verdict, every approval is timestamped and frozen. Edit a policy a year later — yesterday's audit doesn't change.",
  },
  {
    label: "Any document, any source",
    detail:
      "PDFs, Word docs, Excel sheets, Google Forms responses. DOCex reads what your team already collects, however they collect it.",
  },
  {
    label: "Briefed, not just processed",
    detail:
      "Claude reads every result and tells you what matters in plain English — not just a table of numbers.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7] text-gray-900">
      {/* Nav — minimal, no clutter */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-[#fafaf7]/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="text-xl font-bold tracking-tight text-gray-900">
            DOCex
          </Link>
          <div className="flex items-center gap-3">
            <Link
              href="/agents/sub-award"
              className="hidden text-sm font-medium text-gray-600 transition hover:text-gray-900 sm:inline"
            >
              Agents
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
          {/* Subtle warm gradient backdrop — barely there, but it changes
              the whole feel from "tool" to "considered" */}
          <div
            aria-hidden
            className="absolute inset-0 -z-10 bg-gradient-to-b from-amber-50/40 via-[#fafaf7] to-[#fafaf7]"
          />
          <div className="mx-auto max-w-5xl px-6 pt-32 pb-24 text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-medium text-gray-600 shadow-sm">
              <Sparkles className="h-3 w-3 text-brand-600" />
              The AI back-office for African NGOs
            </div>

            <h1 className="mt-8 text-5xl font-semibold leading-[1.05] tracking-tight text-gray-900 sm:text-6xl md:text-7xl">
              Stop reading every document.
              <br />
              <span className="text-brand-600">Start doing the work.</span>
            </h1>

            <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-gray-600 sm:text-xl">
              DOCex reads your applicant files, verifies your payments, and
              checks your compliance — the things finance, programs, and
              sub-award teams spend weeks on. Built for how African NGOs
              actually work.
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
                See how it works →
              </Link>
            </div>
            <p className="mt-5 text-xs text-gray-400">
              No account required · Your documents stay on your machine
            </p>
          </div>
        </section>

        {/* ─── Three agents, one back-office ────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-20 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                Three agents, one back-office
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Built for the work that costs you weeks.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                DOCex isn't a chatbot or a dashboard. It's three named agents,
                each replacing the document-heavy parts of a specific role on
                your team. They share an engine, an audit trail, and a price
                tag.
              </p>
            </div>

            <div className="space-y-4">
              {agents.map((a, i) => (
                <Link
                  key={a.name}
                  href={a.href}
                  className="group flex flex-col gap-6 rounded-3xl border border-gray-100 bg-white p-8 transition hover:border-brand-200 hover:shadow-card-hover sm:flex-row sm:items-center sm:gap-10 sm:p-10"
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

        {/* ─── The Assistant moment ─────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-[#fafaf7]">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="grid items-center gap-16 lg:grid-cols-2">
              <div>
                <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                  The Assistant
                </p>
                <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                  Briefed by Claude. Not just processed.
                </h2>
                <p className="mt-5 text-lg leading-relaxed text-gray-600">
                  Every time an agent finishes a run, Claude reads the result
                  and writes you a plain-English brief. What happened. What
                  matters. What to do next. The verdict table is still there
                  — but you don't have to read it first.
                </p>
                <p className="mt-4 text-sm text-gray-500">
                  No spreadsheets to interpret. No dashboards to learn. Just
                  a colleague who reads everything for you and tells you what
                  to do.
                </p>
              </div>

              {/* Stylised Assistant brief card — same visual language as the
                  real component in /components/AssistantBrief.tsx. The text
                  is a real example from a Bank Verify result. */}
              <div className="overflow-hidden rounded-3xl border border-brand-100 bg-gradient-to-br from-brand-50/30 via-white to-white p-6 shadow-card sm:p-8">
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold uppercase tracking-widest text-brand-700">
                      DOCex Assistant
                    </p>
                    <p className="mt-3 text-base font-semibold leading-snug text-gray-900">
                      4 of 5 accounts cleared. One blocker.
                    </p>
                    <p className="mt-2 text-sm leading-relaxed text-gray-700">
                      Mohammed Farid Abdurraman matched 100% — release this
                      payment. Faridah Abdurraman is likely a typo of the same
                      name; safe to release after a confirm with the team.
                      Aisha Bello has a completely different name on
                      Mohammed's account — recommend blocking pending review.
                    </p>
                    <div className="mt-5 space-y-1.5">
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
                        Suggested next steps
                      </p>
                      <div className="flex flex-wrap gap-2 pt-1">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                          Block Aisha pending review
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                          Confirm Faridah with programs
                        </span>
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-700 ring-1 ring-gray-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
                          Release verified payment
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Trust / built for ────────────────────────────────────────── */}
        <section className="border-t border-gray-100 bg-white">
          <div className="mx-auto max-w-6xl px-6 py-32">
            <div className="mb-16 max-w-2xl">
              <p className="text-sm font-semibold uppercase tracking-widest text-brand-600">
                Built for African NGOs
              </p>
              <h2 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight text-gray-900 sm:text-5xl">
                Designed for how the work actually happens.
              </h2>
              <p className="mt-5 text-lg leading-relaxed text-gray-600">
                Not retrofitted from a US grant-management tool. Built around
                Paystack, Nigerian banks, NDPR, Google Forms — the shape your
                team already runs.
              </p>
            </div>

            <div className="grid gap-8 sm:grid-cols-2">
              {trust.map((t) => (
                <div
                  key={t.label}
                  className="rounded-2xl border border-gray-100 bg-[#fafaf7] p-7"
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
              Spin up the agents you need. Run them on your real files. See
              what a week of work feels like in three minutes.
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
                Tour the agents →
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer — minimal, calm, no link soup */}
      <footer className="border-t border-gray-100 bg-[#fafaf7] py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-gray-400 sm:flex-row">
          <p>DOCex · The AI back-office for African NGOs</p>
          <p>Built with Claude · Powered by Paystack</p>
        </div>
      </footer>
    </div>
  );
}
