"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Clock,
  Loader2,
  Plus,
  UserCheck,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  createTimesheet,
  myTimesheets,
  pendingApproval,
  periodSummary,
} from "@/lib/timesheetApi";
import type { PeriodSummary, TimesheetStatus, TimesheetSummary } from "@/types/timesheet";

/**
 * Timesheets — the landing screen.
 *
 * Two audiences, so two questions answered in order:
 *
 *   "What do I owe?"        — my sheets, and a one-click start for a month I
 *                             have not filled in yet.
 *   "What is waiting on me?" — sheets my team submitted. Never my own: the
 *                             engine refuses self-approval, so showing it in an
 *                             approval queue would only invite the attempt.
 *
 * Finance gets the third question — is payroll safe to run — because a payroll
 * run built on unapproved effort is the finding this whole module prevents.
 */

const STATUS_LABEL: Record<TimesheetStatus, string> = {
  draft: "Not submitted",
  submitted: "Waiting for approval",
  approved: "Approved",
  returned: "Sent back to you",
  processed: "Used in payroll",
};

const STATUS_STYLE: Record<TimesheetStatus, string> = {
  draft: "bg-gray-50 text-gray-600 ring-gray-200",
  submitted: "bg-blue-50 text-blue-700 ring-blue-200",
  approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  returned: "bg-orange-50 text-orange-700 ring-orange-200",
  processed: "bg-indigo-50 text-indigo-700 ring-indigo-200",
};

function periodLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

/** Recent months, newest first. A timesheet is after-the-fact, so the current
 *  month is included but a future one is never offered. */
function recentPeriods(count = 4): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

export default function TimesheetsPage() {
  const router = useRouter();
  const [mine, setMine] = useState<TimesheetSummary[]>([]);
  const [pending, setPending] = useState<TimesheetSummary[]>([]);
  const [summary, setSummary] = useState<PeriodSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const periods = useMemo(() => recentPeriods(4), []);
  const lastMonth = periods[1] ?? periods[0];

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([myTimesheets(), pendingApproval().catch(() => [])]);
      setMine(m);
      setPending(p);
      try {
        setSummary(await periodSummary(lastMonth));
      } catch {
        /* summary is context; a missing one should not blank the screen */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load timesheets.");
    } finally {
      setLoading(false);
    }
  }, [lastMonth]);

  useEffect(() => {
    load();
  }, [load]);

  async function start(period: string) {
    setCreating(period);
    setError(null);
    try {
      const sheet = await createTimesheet({ period });
      router.push(`/timesheets/${sheet.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start that timesheet.");
      setCreating(null);
    }
  }

  const filled = new Set(mine.map((t) => t.period));
  const unfilled = periods.filter((p) => !filled.has(p));

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 p-8 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6 pb-16">
        <header>
          <h1 className="text-xl font-semibold text-gray-900">Timesheets</h1>
          <p className="mt-1 text-sm text-gray-600">
            Record what you actually worked on. Approved hours decide what each
            grant is charged for your salary.
          </p>
        </header>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        )}

        {unfilled.length > 0 && (
          <section className="rounded-xl border border-blue-200 bg-blue-50/50 p-5">
            <h2 className="flex items-center gap-2 font-medium text-gray-900">
              <CalendarDays className="h-4 w-4 text-blue-600" />
              Start a timesheet
            </h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {unfilled.map((p) => (
                <button
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  disabled={creating !== null}
                  key={p}
                  onClick={() => start(p)}
                  type="button"
                >
                  {creating === p ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  {periodLabel(p)}
                </button>
              ))}
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            <Clock className="h-4 w-4" />
            My timesheets
          </h2>
          {mine.length === 0 ? (
            <p className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
              Nothing yet. Start with the month above.
            </p>
          ) : (
            <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
              {mine.map((t) => (
                <Link
                  className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-gray-50"
                  href={`/timesheets/${t.id}`}
                  key={t.id}
                >
                  <div className="min-w-0">
                    <span className="font-medium text-gray-900">
                      {periodLabel(t.period)}
                    </span>
                    <span className="ml-2 text-gray-500">
                      {t.total_hours} hours across {t.projects.length} project
                      {t.projects.length === 1 ? "" : "s"}
                    </span>
                    {t.status === "returned" && t.returned_reason && (
                      <p className="mt-0.5 text-xs text-orange-700">
                        {t.returned_reason}
                      </p>
                    )}
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLE[t.status]}`}
                  >
                    {STATUS_LABEL[t.status]}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </section>

        {pending.length > 0 && (
          <section>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
              <UserCheck className="h-4 w-4" />
              Waiting for your approval
            </h2>
            <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
              {pending.map((t) => (
                <Link
                  className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-gray-50"
                  href={`/timesheets/${t.id}`}
                  key={t.id}
                >
                  <div className="min-w-0">
                    <span className="font-medium text-gray-900">
                      {t.staff_name || t.staff_id}
                    </span>
                    <span className="ml-2 text-gray-500">
                      {periodLabel(t.period)} · {t.total_hours} hours
                    </span>
                  </div>
                  <span className="shrink-0 text-xs font-medium text-blue-700">
                    Review →
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {summary && summary.timesheets > 0 && (
          <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="flex items-center gap-2 font-medium text-gray-900">
              <ClipboardList className="h-4 w-4 text-gray-500" />
              {periodLabel(summary.period)} — before payroll runs
            </h2>
            {summary.ready_for_payroll ? (
              <p className="mt-2 flex items-start gap-2 text-sm text-emerald-800">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                All {summary.timesheets} timesheets are approved. Payroll can
                charge each grant for the hours actually worked.
              </p>
            ) : (
              <p className="mt-2 text-sm text-amber-800">
                Waiting on {summary.outstanding_staff.length} person
                {summary.outstanding_staff.length === 1 ? "" : "s"}:{" "}
                {summary.outstanding_staff.slice(0, 5).join(", ")}
                {summary.outstanding_staff.length > 5 ? "…" : ""}. Until these are
                approved, payroll falls back to budgeted percentages — which a
                donor may disallow.
              </p>
            )}
            {Object.keys(summary.hours_by_project).length > 0 && (
              <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
                {Object.entries(summary.hours_by_project)
                  .sort((a, b) => b[1] - a[1])
                  .map(([code, hours]) => (
                    <div className="flex gap-2" key={code}>
                      <dt className="text-gray-500">{code}</dt>
                      <dd className="font-medium text-gray-900">{hours}h</dd>
                    </div>
                  ))}
              </dl>
            )}
          </section>
        )}
      </div>
    </AppShell>
  );
}
