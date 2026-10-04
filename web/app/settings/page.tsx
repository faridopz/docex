"use client";

/**
 * Settings — every administrator setting on one page, grouped by what it is
 * for. Replaces up to eight separate links in the sidebar footer.
 *
 * Items appear only when the organisation has the capability switched on
 * (the same flags the old links used), so a client never sees a setting for
 * something they don't have.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Banknote,
  Building2,
  ChevronRight,
  KeyRound,
  Landmark,
  Percent,
  ScrollText,
  ShieldCheck,
  Timer,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Page } from "@/components/layout/Page";
import { useAuth } from "@/lib/auth";
import { DEFAULT_CLIENT_CONFIG, getClientConfig, type ClientConfig } from "@/lib/orgConfig";

type Item = { href: string; label: string; hint: string; icon: LucideIcon; show: (c: ClientConfig) => boolean };

const always = () => true;
const flag = (f: string) => (c: ClientConfig) => c.features[f] === true;
const module_ = (m: string) => (c: ClientConfig) => (c.modules as string[]).includes(m);

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "Your organisation",
    items: [
      { href: "/onboarding", label: "Setup wizard", hint: "Six questions: who approves, from what amount, and what paperwork", icon: Wand2, show: always },
      { href: "/settings/org", label: "Organisation", hint: "Name, currency, which features are on", icon: Building2, show: always },
      { href: "/settings/departments", label: "Departments & approval chain", hint: "Who approves what, in which order", icon: Users, show: always },
      { href: "/settings/users", label: "People & access", hint: "Invite staff, set roles, reset passwords", icon: KeyRound, show: always },
      { href: "/settings/timesheets", label: "Timesheets", hint: "On or off; by day, week or month; closing a month; who signs", icon: Timer, show: always },
    ],
  },
  {
    title: "Money",
    items: [
      { href: "/settings/accounts", label: "Bank accounts", hint: "The accounts payments are made from, for month-end", icon: Landmark, show: flag("bank_reconciliation") },
      { href: "/settings/accounting", label: "QuickBooks", hint: "Which QuickBooks you use and how accounts map", icon: Banknote, show: flag("accounting_export") },
      { href: "/settings/withholding", label: "Withholding tax", hint: "Rates deducted from vendor payments", icon: Percent, show: flag("withholding_tax") },
    ],
  },
  {
    title: "Policies & checks",
    items: [
      { href: "/compliance", label: "Policy documents", hint: "Upload your finance or donor policy; payments are checked against it", icon: ShieldCheck, show: module_("compliance") },
      { href: "/compliance/checks", label: "Policy check history", hint: "Every AI policy check run, with its verdict", icon: ScrollText, show: module_("compliance") },
    ],
  },
  {
    title: "You",
    items: [
      { href: "/settings/security", label: "Sign-in & security", hint: "Your password and two-step sign-in", icon: ShieldCheck, show: always },
    ],
  },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const [config, setConfig] = useState<ClientConfig>(DEFAULT_CLIENT_CONFIG);
  useEffect(() => {
    getClientConfig().then(setConfig).catch(() => {
      /* defaults: flagged items stay hidden */
    });
  }, []);

  if (user && user.role !== "admin") {
    // Non-admins reach only their own security settings; say so rather than
    // show a page of links that would each answer "not allowed".
    return (
      <AppShell>
        <Page width="narrow" title="Settings">
          <Link href="/settings/security" className="text-sm font-medium text-brand-700 underline">
            Your sign-in & security settings
          </Link>
        </Page>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <Page width="narrow" title="Settings" subtitle="Everything an administrator sets up, in one place.">
        {GROUPS.map((g) => {
          const items = g.items.filter((i) => i.show(config));
          if (!items.length) return null;
          return (
            <section key={g.title}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{g.title}</h2>
              <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 bg-white">
                {items.map((i) => (
                  <li key={i.href}>
                    <Link href={i.href} className="flex items-center gap-3 px-4 py-3.5 transition hover:bg-gray-50">
                      <i.icon className="h-4 w-4 shrink-0 text-gray-400" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-gray-900">{i.label}</span>
                        <span className="block text-xs text-gray-500">{i.hint}</span>
                      </span>
                      <ChevronRight className="h-4 w-4 shrink-0 text-gray-300" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </Page>
    </AppShell>
  );
}
