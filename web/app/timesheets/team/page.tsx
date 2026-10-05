"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, BellRing, Loader2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { remindOutstanding, teamView } from "@/lib/timesheetApi";
import type { TeamRow, TeamView } from "@/types/timesheet";

/**
 * Everyone's month on one screen, for supervisors (their department) and
 * Finance (the whole organisation): who needs reviewing, who is done, who
 * has entries to fix, and who hasn't started — with the reminder one click
 * away.
 */

const STATUS: Record<TeamRow["status"], { label: string; cls: string }> = {
  not_started: { label: "Not started", cls: "bg-gray-50 text-gray-500 ring-gray-200" },
  draft: { label: "Not sent", cls: "bg-gray-50 text-gray-600 ring-gray-200" },
  submitted: { label: "Needs review", cls: "bg-blue-50 text-blue-700 ring-blue-200" },
  returned: { label: "Back with them", cls: "bg-orange-50 text-orange-700 ring-orange-200" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  processed: { label: "Used in payroll", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200" },
};

type Filter = "all" | "needs_review" | "approved" | "has_rejections" | "not_started";

function months(count = 6): string[] {
  const now = new Date();
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
}

function label(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export default function TeamTimesheetsPage() {
  const periods = useMemo(() => months(6), []);
  const [period, setPeriod] = useState(periods[1] ?? periods[0]);
  const [data, setData] = useState<TeamView | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [reminding, setReminding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await teamView(period));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the team view.");
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  async function remind() {
    setReminding(true);
    setNote(null);
    try {
      const r = await remindOutstanding(period);
      setNote(r.reminded
        ? `Reminded ${r.reminded} ${r.reminded === 1 ? "person" : "people"}${r.emailed ? ` (${r.emailed} by email too)` : ""}.`
        : "Everyone's timesheet is already in.");
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not send reminders.");
    } finally {
      setReminding(false);
    }
  }

  const rows = (data?.rows ?? []).filter((r) =>
    filter === "all" ? true
      : filter === "needs_review" ? r.status === "submitted"
      : filter === "approved" ? r.status === "approved" || r.status === "processed"
      : filter === "has_rejections" ? r.entry_counts.rejected > 0
      : r.status === "not_started");
  const owing = (data?.rows ?? []).filter((r) => ["not_started", "draft", "returned"].includes(r.status)).length;

  const tiles: [Filter, string, number, string][] = data ? [
    ["needs_review", "Needs review", data.counters.needs_review, "text-blue-700"],
    ["approved", "Approved", data.counters.approved, "text-emerald-700"],
    ["has_rejections", "Entries to fix", data.counters.has_rejections, "text-red-700"],
    ["not_started", "Not started", data.counters.not_started, "text-gray-700"],
  ] : [];

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-5 pb-16 py-6 sm:px-6 lg:px-8">
        <Link href="/timesheets" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-4 w-4" /> Timesheets
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Team timesheets</h1>
            <p className="mt-1 text-sm text-gray-600">Who has sent their time, who needs you, and who hasn&apos;t started.</p>
          </div>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
            {periods.map((p) => <option key={p} value={p}>{label(p)}</option>)}
          </select>
        </div>

        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}

        {loading ? (
          <div className="flex items-center gap-2 p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : data && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {tiles.map(([key, title, value, cls]) => (
                <button key={key} type="button" onClick={() => setFilter(filter === key ? "all" : key)}
                        className={`rounded-xl border bg-white p-4 text-left shadow-sm transition ${
                          filter === key ? "border-blue-600 ring-1 ring-blue-600" : "border-gray-200 hover:border-gray-300"}`}>
                  <p className="text-xs font-medium text-gray-500">{title}</p>
                  <p className={`mt-1 text-2xl font-semibold ${cls}`}>{value}</p>
                </button>
              ))}
            </div>

            {owing > 0 && (
              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 text-sm shadow-sm">
                <BellRing className="h-4 w-4 text-gray-500" />
                <span className="flex-1 text-gray-700">
                  {owing} {owing === 1 ? "person hasn't" : "people haven't"} sent {label(period)} yet.
                </span>
                <button type="button" onClick={remind} disabled={reminding}
                        className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                  {reminding ? "Sending…" : "Send a reminder"}
                </button>
                {note && <span className="w-full text-emerald-700">{note}</span>}
              </div>
            )}

            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <th className="px-4 py-2.5">Person</th>
                    <th className="px-4 py-2.5">Department</th>
                    <th className="px-4 py-2.5 text-right">Hours</th>
                    <th className="px-4 py-2.5">Entries</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.length === 0 && (
                    <tr><td colSpan={6} className="px-4 py-6 text-center text-gray-400">Nobody here.</td></tr>
                  )}
                  {rows.map((r) => {
                    const st = STATUS[r.status];
                    return (
                      <tr key={r.staff_id}>
                        <td className="px-4 py-3">
                          <p className="font-medium text-gray-900">{r.name}</p>
                          <p className="text-xs text-gray-500">{r.staff_id}</p>
                        </td>
                        <td className="px-4 py-3 capitalize text-gray-600">{r.department || "—"}</td>
                        <td className="px-4 py-3 text-right font-medium text-gray-900">{r.total_hours || "—"}</td>
                        <td className="px-4 py-3 text-xs">
                          {r.entry_counts.approved > 0 && <span className="mr-2 text-emerald-700">{r.entry_counts.approved} approved</span>}
                          {r.entry_counts.pending > 0 && <span className="mr-2 text-amber-700">{r.entry_counts.pending} waiting</span>}
                          {r.entry_counts.rejected > 0 && <span className="text-red-700">{r.entry_counts.rejected} rejected</span>}
                          {!r.timesheet_id && <span className="text-gray-400">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${st.cls}`}>
                            {r.status === "submitted" && r.stage === "second" ? "Second signature" : st.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {r.timesheet_id && (
                            <Link href={`/timesheets/${r.timesheet_id}`} className="text-sm font-medium text-blue-600 hover:underline">
                              {r.status === "submitted" ? "Review" : "Open"}
                            </Link>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
