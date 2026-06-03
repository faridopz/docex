import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CalendarCheck,
  FileSearch,
  Landmark,
  Layers,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { AppNav } from "@/components/AppNav";

/**
 * /home — the in-product launcher.
 *
 * A grouped, tiled overview of every capability so nothing (including the
 * standalone Bank Verify one-off check) is more than one click away. The
 * AppNav brand links here; the public marketing page stays at "/".
 */

type Tile = {
  icon: LucideIcon;
  name: string;
  blurb: string;
  href: string;
  cta: string;
};

const GROUPS: { label: string; tiles: Tile[] }[] = [
  {
    label: "Documents",
    tiles: [
      {
        icon: FileSearch,
        name: "Extract",
        blurb:
          "Ask questions across a stack of documents — answers with source, quote, and confidence.",
        href: "/app",
        cta: "Start an extraction",
      },
      {
        icon: Layers,
        name: "Templates",
        blurb:
          "Save and reuse the questions your team asks every time. Run them on every batch.",
        href: "/templates",
        cta: "Open the library",
      },
      {
        icon: BookOpen,
        name: "Knowledge",
        blurb:
          "Ask your library of decks and reports a question and get a cited answer.",
        href: "/knowledge",
        cta: "Open knowledge",
      },
    ],
  },
  {
    label: "Payments & Compliance",
    tiles: [
      {
        icon: ShieldCheck,
        name: "Compliance",
        blurb:
          "Check a payment against one or more policy sets, rule by rule, with an audit trail.",
        href: "/compliance/check",
        cta: "Check a payment",
      },
      {
        icon: Landmark,
        name: "Bank Verify",
        blurb:
          "A one-off check: confirm a recipient's name matches the bank-of-record holder.",
        href: "/verify/new",
        cta: "Run a check",
      },
      {
        icon: CalendarCheck,
        name: "Attendance & Payment",
        blurb:
          "Turn an attendance log + payment list into a verified payment schedule.",
        href: "/agents/attendance-payment",
        cta: "Open the flow",
      },
    ],
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <AppNav />

      <main className="mx-auto max-w-5xl px-6 py-12">
        <header className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            What would you like to do?
          </h1>
          <p className="mt-2 max-w-2xl text-base text-gray-600">
            Every capability, one click away. Pick a tool, or start from a
            saved template.
          </p>
        </header>

        <div className="space-y-10">
          {GROUPS.map((group) => (
            <section key={group.label}>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                {group.label}
              </h2>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {group.tiles.map((t) => (
                  <Link
                    key={t.name}
                    href={t.href}
                    className="group flex flex-col rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition hover:border-brand-200 hover:shadow-card-hover"
                  >
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
                      <t.icon className="h-5 w-5" />
                    </div>
                    <h3 className="mt-4 text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
                      {t.name}
                    </h3>
                    <p className="mt-1.5 flex-1 text-sm leading-relaxed text-gray-600">
                      {t.blurb}
                    </p>
                    <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700">
                      {t.cta}
                      <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
