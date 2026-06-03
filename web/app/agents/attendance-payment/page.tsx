"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  CalendarDays,
  ChevronRight,
  CircleDollarSign,
  Loader2,
  Plus,
  Sparkles,
  Users,
} from "lucide-react";
import { listAttendanceRuns } from "@/lib/api";
import { AppNav } from "@/components/AppNav";
import { GuidanceCard } from "@/components/GuidanceCard";
import type { AttendancePaymentRunSummary } from "@/types";

/**
 * Attendance & Payment Flow — landing page.
 *
 * Shows every past run, jump back into any of them, or start a new one.
 * Mirrors the /verify and /compliance landings so the user's eye doesn't
 * have to retrain layout per agent.
 *
 * This is also the first surface for the "Agents" concept in /app's
 * navigation. As we add more composite agents (Sub-award Co-Pilot, Procurement
 * Agent), each gets a sibling route under /agents/.
 */

export default function AttendanceAgentLandingPage() {
  const [runs, setRuns] = useState<AttendancePaymentRunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listAttendanceRuns();
        if (!cancelled) setRuns(list);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load runs. Is the API running on port 8000?",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <AppNav active="attendance">
        <Link
          href="/rate-cards"
          className="hidden items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 sm:inline-flex"
        >
          Rate cards
        </Link>
        <Link
          href="/agents/attendance-payment/new"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          <Plus className="h-3.5 w-3.5" />
          New run
        </Link>
      </AppNav>

      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="space-y-8">
          {/* Page header */}
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Attendance to paid, in three minutes.
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Upload the attendance log and the payment info form. DOCex
                cross-checks who attended, calculates{" "}
                <span className="text-gray-900">days × rate</span>, flags
                anyone you can&apos;t verify, and hands the schedule straight
                to Bank Verify — so finance gets a clean file, not a guess.
              </p>
            </div>
            {runs && runs.length > 0 && (
              <Link
                href="/agents/attendance-payment/new"
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              >
                <Plus className="h-4 w-4" />
                New run
              </Link>
            )}
          </div>

          <GuidanceCard title="How this agent works">
            Two inputs. The <span className="font-medium">attendance log</span>{" "}
            is the one filled in during the event (name + a tick per day
            attended). The{" "}
            <span className="font-medium">payment info form</span> is the one
            registered participants fill in once (name + organisation +
            account + bank). DOCex matches every payee to their attendance,
            calculates days × rate, and flags anyone who's on one list but not
            the other — so finance doesn't pay someone who didn't show up, and
            the team can chase down missing bank info for anyone who did.
          </GuidanceCard>

          {error && (
            <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <p className="font-medium text-red-900">Could not load runs</p>
              <p>{error}</p>
            </div>
          )}

          {runs === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading runs…
            </div>
          )}

          {runs !== null && runs.length === 0 && !error && <EmptyState />}

          {runs !== null && runs.length > 0 && (
            <div className="grid gap-3">
              {runs.map((r) => (
                <RunCard key={r.run_id} run={r} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <Users className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        Run your first event payment
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Pick an event, upload the attendance log and the payment info form,
        set the per-diem rate, and DOCex builds the verified payment
        schedule in under a minute.
      </p>
      <Link
        href="/agents/attendance-payment/new"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700"
      >
        <Sparkles className="h-4 w-4" />
        Start a new run
      </Link>
      <p className="mt-4 text-xs text-gray-400">
        Two .xlsx uploads · auto-matches names · 3 minutes end-to-end
      </p>
    </div>
  );
}

function RunCard({ run }: { run: AttendancePaymentRunSummary }) {
  const created = run.created_at ? new Date(run.created_at) : null;
  return (
    <Link
      href={`/agents/attendance-payment/${run.run_id}`}
      className="group block rounded-xl border border-gray-200 bg-white p-5 transition hover:border-brand-300 hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold text-gray-900 transition-colors group-hover:text-brand-700">
            {run.event_name}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="h-3 w-3 shrink-0" />
              {run.days_in_event}{" "}
              {run.days_in_event === 1 ? "day" : "days"}
            </span>
            <span className="inline-flex items-center gap-1">
              <CircleDollarSign className="h-3 w-3 shrink-0" />
              ₦{run.rate_per_day.toLocaleString()}/day
            </span>
            {run.bank_verify_batch_id && (
              <span className="inline-flex items-center gap-1 text-emerald-600">
                Bank Verify run ✓
              </span>
            )}
          </div>
        </div>
        <ChevronRight className="h-5 w-5 shrink-0 text-gray-300 transition-colors group-hover:text-brand-600" />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1.5">
        {run.paid_count > 0 && (
          <Pill tone="emerald" count={run.paid_count} label="paid" />
        )}
        {run.no_attendance_count > 0 && (
          <Pill
            tone="rose"
            count={run.no_attendance_count}
            label="no attendance"
          />
        )}
        {run.no_payment_info_count > 0 && (
          <Pill
            tone="amber"
            count={run.no_payment_info_count}
            label="no bank info"
          />
        )}
        <span className="ml-auto text-xs font-medium text-gray-700">
          ₦{run.total_to_pay.toLocaleString()}
        </span>
        {created && (
          <span className="text-xs text-gray-400">
            · {formatRelative(created)}
          </span>
        )}
      </div>
    </Link>
  );
}

function Pill({
  tone,
  count,
  label,
}: {
  tone: "emerald" | "rose" | "amber";
  count: number;
  label: string;
}) {
  const styles: Record<typeof tone, string> = {
    emerald: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    rose: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
    amber: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  };
  const dots: Record<typeof tone, string> = {
    emerald: "bg-emerald-500",
    rose: "bg-rose-500",
    amber: "bg-amber-400",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${styles[tone]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />
      {count} {label}
    </span>
  );
}

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
