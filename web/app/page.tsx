import Link from "next/link";
import { ArrowRight, BarChart3, Clock, FileSearch, Sparkles, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const benefits = [
  {
    icon: Sparkles,
    title: "You define what to look for",
    desc: "Describe your criteria in plain language. DOCex trains on your exact requirements — not a generic template.",
  },
  {
    icon: FileSearch,
    title: "Upload anything, in bulk",
    desc: "Drag and drop PDFs, Word docs, and text files all at once. Grant applications, CVs, contracts, bids — any documents that arrive in volume.",
  },
  {
    icon: BarChart3,
    title: "Get structured answers instantly",
    desc: "Every document scored, ranked, and summarised. Key findings surfaced. Red flags flagged. Ready to act on in minutes.",
  },
];

const steps = [
  { n: "01", label: "Define your criteria" },
  { n: "02", label: "Upload your documents" },
  { n: "03", label: "Review ranked results" },
];

// Each card links somewhere — extraction-flavoured cases all go to /app,
// the compliance card routes to /compliance. Better than passive copy.
const useCases: { label: string; desc: string; href: string }[] = [
  { label: "Grant applications", desc: "Shortlist partners from 200 submissions in an afternoon", href: "/app" },
  { label: "CV screening", desc: "Score candidates against a job spec automatically", href: "/app" },
  { label: "Supplier bids", desc: "Extract and compare key terms across proposals", href: "/app" },
  { label: "Compliance docs", desc: "Check payments against your policy in seconds — receipts, vendors, approvals, all flagged", href: "/compliance" },
];

const socialProof = [
  "Read 100 documents in the time it takes to read 3",
  "Consistent scoring — no reviewer fatigue",
  "Never miss a critical clause or disqualifying factor",
  "Export a clean summary for your team in one click",
];

export default function LandingPage() {
  return (
    <div className="flex flex-col min-h-screen bg-white">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white/90 backdrop-blur-sm">
        <div className="mx-auto max-w-6xl px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold text-brand-600 tracking-tight">DOCex</span>
          <Link href="/app">
            <Button size="sm">Start extracting</Button>
          </Link>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-6 pt-24 pb-20 text-center">
          <div className="inline-flex items-center gap-2 rounded-full bg-brand-50 border border-brand-100 px-4 py-1.5 text-sm text-brand-700 font-medium mb-8">
            <Sparkles className="w-4 h-4" />
            Powered by Claude AI
          </div>

          <h1 className="text-5xl sm:text-6xl font-bold text-gray-900 leading-[1.1] mb-6">
            Tell it what to find.
            <br />
            <span className="text-brand-600">It reads every document.</span>
          </h1>

          <p className="text-xl text-gray-500 max-w-2xl mx-auto mb-10 leading-relaxed">
            Upload any documents in bulk — applications, CVs, contracts, bids.
            Define exactly what you&apos;re looking for. Get every document scored,
            ranked, and summarised instantly.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/app">
              <Button size="lg" className="gap-2 shadow-md shadow-brand-100">
                Start extracting for free
                <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
            <p className="text-sm text-gray-400">No account required · No setup</p>
          </div>
        </section>

        {/* Before / After */}
        <section className="bg-gray-50 border-y border-gray-100">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <div className="grid md:grid-cols-2 gap-8 items-center">

              {/* Before */}
              <div className="rounded-2xl border border-red-100 bg-white p-8 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-widest text-red-400 mb-4">Before</p>
                <h3 className="text-xl font-semibold text-gray-800 mb-6">The old way</h3>
                <ul className="space-y-3">
                  {[
                    "Open 80 documents one by one",
                    "Read each one line by line (45 min avg)",
                    "Try to remember what you read 3 hours ago",
                    "Spreadsheet with half-filled columns",
                    "Miss the critical clause on page 7",
                    "Two weeks of work, still not confident",
                  ].map((item) => (
                    <li key={item} className="flex items-start gap-3 text-sm text-gray-600">
                      <span className="mt-0.5 text-red-300 font-bold">✕</span>
                      {item}
                    </li>
                  ))}
                </ul>
                <div className="mt-6 rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm font-medium text-red-600 flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Average: days of staff time per batch
                </div>
              </div>

              {/* After */}
              <div className="rounded-2xl border border-emerald-100 bg-white p-8 shadow-card">
                <p className="text-xs font-semibold uppercase tracking-widest text-emerald-500 mb-4">After</p>
                <h3 className="text-xl font-semibold text-gray-800 mb-6">With DOCex</h3>
                <ul className="space-y-3">
                  {[
                    "Drag and drop all your files at once",
                    "AI reads and scores every document",
                    "Same criteria applied consistently to all",
                    "Ranked results with colour-coded scores",
                    "Critical factors auto-flagged",
                    "One-click export for your team",
                  ].map((item) => (
                    <li key={item} className="flex items-start gap-3 text-sm text-gray-600">
                      <CheckCircle2 className="mt-0.5 w-4 h-4 text-emerald-500 flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
                <div className="mt-6 rounded-lg bg-emerald-50 border border-emerald-100 px-4 py-3 text-sm font-medium text-emerald-700 flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  Average: under 10 minutes
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Use cases */}
        <section className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">Works for any documents</h2>
          <p className="text-center text-gray-500 mb-14 max-w-xl mx-auto">
            If it arrives in bulk and needs to be read carefully, DOCex can handle it.
          </p>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4">
            {useCases.map((u) => (
              <Link
                key={u.label}
                href={u.href}
                className="group rounded-2xl border border-gray-100 bg-white p-6 shadow-card transition hover:border-brand-200 hover:shadow-card-hover"
              >
                <p className="font-semibold text-gray-900 mb-2 transition-colors group-hover:text-brand-700">{u.label}</p>
                <p className="text-sm text-gray-500 leading-relaxed">{u.desc}</p>
              </Link>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="bg-gray-50 border-y border-gray-100">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">How it works</h2>
            <p className="text-center text-gray-500 mb-14 max-w-xl mx-auto">
              Three steps from upload to answers.
            </p>
            <div className="flex flex-col sm:flex-row items-start gap-0 sm:gap-0 relative">
              {steps.map((s, i) => (
                <div key={s.n} className="flex flex-1 flex-col items-center text-center px-6 relative">
                  <div className="w-12 h-12 rounded-full bg-brand-600 text-white font-bold text-lg flex items-center justify-center mb-4 shadow-md shadow-brand-100">
                    {s.n}
                  </div>
                  {i < steps.length - 1 && (
                    <div className="hidden sm:block absolute top-6 left-[calc(50%+24px)] right-0 h-px bg-brand-100 z-0" />
                  )}
                  <p className="font-semibold text-gray-800 text-base">{s.label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Benefits */}
        <section className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">Everything you need</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {benefits.map((b) => (
              <div key={b.title} className="bg-white rounded-2xl p-8 shadow-card border border-gray-100">
                <div className="w-10 h-10 rounded-lg bg-brand-50 flex items-center justify-center mb-5">
                  <b.icon className="w-5 h-5 text-brand-600" />
                </div>
                <h3 className="font-semibold text-gray-900 mb-2 text-lg">{b.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{b.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Social proof */}
        <section className="bg-gray-50 border-y border-gray-100">
          <div className="mx-auto max-w-3xl px-6 py-20 text-center">
            <h2 className="text-3xl font-bold text-gray-900 mb-10">Built for teams who read too much</h2>
            <div className="grid sm:grid-cols-2 gap-4">
              {socialProof.map((p) => (
                <div key={p} className="flex items-center gap-3 rounded-xl border border-gray-100 bg-white px-5 py-4 text-sm text-gray-700 shadow-card">
                  <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                  {p}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="bg-brand-600 py-20 text-center text-white">
          <h2 className="text-4xl font-bold mb-4">Ready to stop reading everything yourself?</h2>
          <p className="text-brand-100 text-lg mb-10 max-w-xl mx-auto">
            No account. No credit card. Upload your documents, define what matters, see the results.
          </p>
          <Link href="/app">
            <Button size="lg" variant="outline" className="bg-white text-brand-700 border-white hover:bg-brand-50 shadow-lg">
              Start extracting for free
              <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
        </section>
      </main>

      <footer className="border-t border-gray-100 py-8 text-center text-sm text-gray-400">
        DOCex · AI-powered document extraction · Built with Claude
      </footer>
    </div>
  );
}
