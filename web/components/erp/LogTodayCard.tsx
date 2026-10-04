"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Clock, Loader2 } from "lucide-react";
import { getClientConfig, hasFeature } from "@/lib/orgConfig";
import { myProjects, quickLog } from "@/lib/timesheetApi";
import type { MyProject } from "@/types/timesheet";

/**
 * "What did you work on today?" — the ten-second timesheet.
 *
 * Tap a project, tap half or full day. That's the whole interaction, and it
 * works on a phone. It writes to the same month's timesheet the full grid
 * edits, so nothing is recorded twice and nothing new has to be learnt by the
 * supervisor who signs it. Shown only when the organisation uses timesheets.
 */
export function LogTodayCard() {
  const [projects, setProjects] = useState<MyProject[] | null>(null);
  const [nonProject, setNonProject] = useState("NON_PROJECT");
  const [picked, setPicked] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheetId, setSheetId] = useState<string | null>(null);
  const [monthHours, setMonthHours] = useState<number | null>(null);

  useEffect(() => {
    // Only for organisations that use timesheets: don't even ask otherwise.
    getClientConfig()
      .then((cfg) => (hasFeature(cfg, "timesheets") ? myProjects() : Promise.reject(new Error("off"))))
      .then((r) => {
        setProjects(r.projects);
        setNonProject(r.non_project);
        if (r.projects.length === 1) setPicked(r.projects[0].project_code);
      })
      .catch(() => setProjects(null));
  }, []);

  if (projects === null) return null;      // timesheets off, or not loaded

  async function log(portion: "half" | "full") {
    if (!picked) {
      setError("Pick what you worked on first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const sheet = await quickLog({ projectCode: picked, portion });
      const label = picked === nonProject ? "leave / admin" : picked;
      setDone(`${portion === "full" ? "A full day" : "Half a day"} on ${label}, recorded for today.`);
      setSheetId(sheet.id);
      setMonthHours(sheet.total_hours);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save.");
    } finally {
      setBusy(false);
    }
  }

  const chip = (code: string, label: string, sub?: string) => (
    <button
      key={code}
      type="button"
      onClick={() => {
        setPicked(code);
        setDone(null);
        setError(null);
      }}
      className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
        picked === code
          ? "border-blue-600 bg-blue-50 text-blue-800 ring-1 ring-blue-600"
          : "border-gray-200 bg-white text-gray-700 hover:border-gray-300"
      }`}
    >
      <div className="font-medium">{label}</div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </button>
  );

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4 text-blue-600" />
        <h2 className="text-sm font-semibold text-gray-900">What did you work on today?</h2>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {projects.map((p) => chip(p.project_code, p.project_code, p.donor || p.title || undefined))}
        {chip(nonProject, "Leave / admin", "Not charged to a grant")}
      </div>
      {projects.length === 0 && (
        <p className="mt-2 text-xs text-gray-500">
          You aren&apos;t on any project yet. Finance adds you to your projects; until then you can record leave or admin,
          or use the full <Link href="/timesheets" className="text-blue-600 underline">timesheet</Link>.
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" disabled={busy} onClick={() => log("full")}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          Full day
        </button>
        <button type="button" disabled={busy} onClick={() => log("half")}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">
          Half day
        </button>
        {busy && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
        <Link href={sheetId ? `/timesheets/${sheetId}` : "/timesheets"} className="ml-auto text-xs text-blue-600 hover:underline">
          Open my timesheet
        </Link>
      </div>
      {done && (
        <p className="mt-3 flex items-center gap-2 text-sm text-emerald-700">
          <CheckCircle2 className="h-4 w-4" /> {done}
          {monthHours != null && <span className="text-gray-500">· {monthHours} hours this month</span>}
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </section>
  );
}
