"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Clock, Loader2, Pencil, Plus, RotateCcw, Trash2, XCircle } from "lucide-react";
import { addItem, clearItem, rejectItem, removeItem, updateItem } from "@/lib/timesheetApi";
import type { EntryStatus, MyProject, Timesheet, TimeEntry } from "@/types/timesheet";

/**
 * A timesheet as a list of entries: add a line (day, project, hours, what
 * you did), see your lines grouped by day, each with its own status.
 *
 * A supervisor rejects single lines with a reason instead of sending back a
 * whole month over one wrong day. Approved lines are locked: they are the
 * record a donor's auditor will ask for. The month grid is still there, as
 * "Month view", for people who prefer it.
 */

const NON_PROJECT = "NON_PROJECT";

const PILL: Record<EntryStatus, { label: string; cls: string }> = {
  pending: { label: "Waiting for review", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  rejected: { label: "Rejected", cls: "bg-red-50 text-red-700 ring-red-200" },
};

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Today if it falls in this month, otherwise the month's last day. */
function defaultDate(period: string): string {
  const today = iso(new Date());
  if (today.startsWith(period)) return today;
  const [y, m] = period.split("-").map(Number);
  return iso(new Date(y, m, 0));
}

function dayHeading(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

interface Props {
  sheet: Timesheet;
  mine: MyProject[];
  /** The signed-in person owns this sheet (they add and edit). */
  isOwner: boolean;
  /** The sheet can take changes from its owner now. */
  editable: boolean;
  onChange: (t: Timesheet) => void;
}

interface Draft {
  date: string;
  project: string;
  other: string;
  hours: string;
  activity: string;
  overtime: boolean;
}

export function TimesheetEntries({ sheet, mine, isOwner, editable, onChange }: Props) {
  const perDay = sheet.hours_per_day ?? 8;
  const blank = (): Draft => ({
    date: defaultDate(sheet.period),
    project: mine[0]?.project_code ?? "",
    other: "",
    hours: "",
    activity: "",
    overtime: false,
  });
  const [draft, setDraft] = useState<Draft>(blank);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const reviewing = sheet.status === "submitted" && !isOwner;
  const counts = sheet.entry_counts ?? { pending: 0, approved: 0, rejected: 0 };

  const name = (code: string) => {
    if (code === NON_PROJECT) return { title: "Leave / admin", sub: "Not charged to a grant" };
    const p = sheet.project_names?.[code] ?? mine.find((m) => m.project_code === code);
    return { title: p?.title || code, sub: [p?.donor, p?.title ? code : ""].filter(Boolean).join(" · ") };
  };

  const choices = useMemo(() => {
    const codes = new Map<string, string>();
    for (const p of mine) codes.set(p.project_code, [p.title || p.project_code, p.donor].filter(Boolean).join(" — "));
    for (const [code, p] of Object.entries(sheet.project_names ?? {}))
      if (!codes.has(code)) codes.set(code, [p.title || code, p.donor].filter(Boolean).join(" — "));
    return Array.from(codes.entries());
  }, [mine, sheet.project_names]);

  const byDay = useMemo(() => {
    const out = new Map<string, TimeEntry[]>();
    for (const e of [...sheet.entries].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))) {
      out.set(e.date, [...(out.get(e.date) ?? []), e]);
    }
    return Array.from(out.entries());
  }, [sheet.entries]);

  async function run(key: string, fn: () => Promise<Timesheet>, after?: () => void) {
    setBusy(key);
    setError(null);
    try {
      onChange(await fn());
      after?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save.");
    } finally {
      setBusy(null);
    }
  }

  function save() {
    const code = draft.project === "__other" ? draft.other.trim().toUpperCase() : draft.project;
    const hours = Number(draft.hours);
    if (!code) return setError("Pick the project you worked on.");
    if (!hours || hours <= 0) return setError("Say how many hours.");
    const item = { date: draft.date, projectCode: code, hours, activity: draft.activity, overtime: draft.overtime };
    run("save",
      () => (editing ? updateItem(sheet.id, editing, item) : addItem(sheet.id, item)),
      () => {
        setEditing(null);
        setDraft({ ...blank(), date: draft.date, project: draft.project, other: draft.other });
      });
  }

  function startEdit(e: TimeEntry) {
    const known = choices.some(([c]) => c === e.project_code) || e.project_code === NON_PROJECT;
    setEditing(e.id);
    setError(null);
    setDraft({
      date: e.date,
      project: known ? e.project_code : "__other",
      other: known ? "" : e.project_code,
      hours: String(e.hours),
      activity: e.activity,
      overtime: e.overtime,
    });
  }

  const tiles: [string, number | string, string][] = [
    ["Hours logged", sheet.total_hours, "text-gray-900"],
    ["Waiting for review", counts.pending, "text-amber-700"],
    ["Approved", counts.approved, "text-emerald-700"],
    ["Rejected", counts.rejected, "text-red-700"],
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map(([label, value, cls]) => (
          <div key={label} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium text-gray-500">{label}</p>
            <p className={`mt-1 text-2xl font-semibold ${cls}`}>{value}</p>
          </div>
        ))}
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      {isOwner && editable && (
        <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            {editing ? <Pencil className="h-4 w-4 text-blue-600" /> : <Plus className="h-4 w-4 text-blue-600" />}
            {editing ? "Change this entry" : "Add an entry"}
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-xs font-medium text-gray-600">
              Day
              <input type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })}
                     min={`${sheet.period}-01`} max={defaultDate(sheet.period)}
                     className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
            </label>
            <label className="text-xs font-medium text-gray-600 lg:col-span-2">
              Project
              <select value={draft.project} onChange={(e) => setDraft({ ...draft, project: e.target.value })}
                      className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm">
                <option value="">Choose…</option>
                {choices.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
                <option value={NON_PROJECT}>Leave / admin / training</option>
                <option value="__other">Another project (type its code)</option>
              </select>
              {draft.project === "__other" && (
                <input value={draft.other} onChange={(e) => setDraft({ ...draft, other: e.target.value })}
                       placeholder="Project code" className="mt-2 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              )}
            </label>
            <label className="text-xs font-medium text-gray-600">
              Hours
              <input inputMode="decimal" value={draft.hours} onChange={(e) => setDraft({ ...draft, hours: e.target.value })}
                     placeholder="e.g. 4" className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
              <span className="mt-1 flex gap-1.5">
                {[["½ day", perDay / 2], ["Full day", perDay]].map(([l, h]) => (
                  <button key={l as string} type="button" onClick={() => setDraft({ ...draft, hours: String(Math.round((h as number) * 100) / 100) })}
                          className="rounded-md border border-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-600 hover:bg-gray-50">
                    {l as string}
                  </button>
                ))}
              </span>
            </label>
          </div>
          <label className="mt-3 block text-xs font-medium text-gray-600">
            What did you do?
            <textarea value={draft.activity} onChange={(e) => setDraft({ ...draft, activity: e.target.value })} rows={2}
                      placeholder="e.g. Community screening in Kubwa; wrote the weekly report"
                      className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={draft.overtime} onChange={(e) => setDraft({ ...draft, overtime: e.target.checked })}
                     className="h-4 w-4 rounded border-gray-300" />
              Overtime
            </label>
            <span className="text-xs text-gray-400">Your supervisor sees this; it doesn&apos;t change pay.</span>
            <div className="ml-auto flex gap-2">
              {editing && (
                <button type="button" onClick={() => { setEditing(null); setDraft(blank()); }}
                        className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
              )}
              <button type="button" onClick={save} disabled={busy !== null}
                      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />}
                {editing ? "Save changes" : "Add entry"}
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="space-y-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
          <Clock className="h-4 w-4" /> Entries
        </h2>
        {byDay.length === 0 && (
          <p className="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
            No entries yet{isOwner && editable ? ". Add your first one above." : "."}
          </p>
        )}
        {byDay.map(([date, entries]) => (
          <div key={date}>
            <div className="mb-2 flex items-baseline justify-between text-sm">
              <span className="font-medium text-gray-800">{dayHeading(date)}</span>
              <span className="text-gray-500">{Math.round(entries.reduce((s, e) => s + e.hours, 0) * 100) / 100}h</span>
            </div>
            <div className="space-y-2">
              {entries.map((e) => {
                const n = name(e.project_code);
                const pill = PILL[e.status];
                const canChange = isOwner && editable && e.status !== "approved";
                return (
                  <div key={e.id} className={`rounded-xl border bg-white p-4 shadow-sm ${e.status === "rejected" ? "border-red-200" : "border-gray-200"}`}>
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900">{n.title}</p>
                        {n.sub && <p className="text-xs text-gray-500">{n.sub}</p>}
                        {e.activity && <p className="mt-1.5 text-sm text-gray-700">{e.activity}</p>}
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-semibold text-gray-900">{e.hours}h</p>
                        <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${pill.cls}`}>
                          {pill.label}
                        </span>
                        {e.overtime && (
                          <span className="ml-1 inline-block rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-inset ring-violet-200">
                            Overtime
                          </span>
                        )}
                      </div>
                    </div>
                    {e.status === "rejected" && e.reject_reason && (
                      <p className="mt-3 rounded-lg bg-red-50 p-2.5 text-sm text-red-800">
                        <span className="font-medium">Why it was rejected:</span> {e.reject_reason}
                      </p>
                    )}
                    {(canChange || (reviewing && e.status !== "approved")) && (
                      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
                        {canChange && (
                          <>
                            <button type="button" onClick={() => startEdit(e)}
                                    className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
                              <Pencil className="h-3.5 w-3.5" /> {e.status === "rejected" ? "Fix it" : "Edit"}
                            </button>
                            <button type="button" disabled={busy !== null}
                                    onClick={() => window.confirm("Remove this entry?") && run(`rm-${e.id}`, () => removeItem(sheet.id, e.id))}
                                    className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50">
                              <Trash2 className="h-3.5 w-3.5" /> Remove
                            </button>
                          </>
                        )}
                        {reviewing && e.status === "pending" && rejecting !== e.id && (
                          <button type="button" onClick={() => { setRejecting(e.id); setReason(""); }}
                                  className="inline-flex items-center gap-1 rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50">
                            <XCircle className="h-3.5 w-3.5" /> Reject
                          </button>
                        )}
                        {reviewing && e.status === "rejected" && (
                          <button type="button" disabled={busy !== null} onClick={() => run(`clr-${e.id}`, () => clearItem(sheet.id, e.id))}
                                  className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
                            <RotateCcw className="h-3.5 w-3.5" /> Undo rejection
                          </button>
                        )}
                        {rejecting === e.id && (
                          <div className="flex w-full flex-wrap gap-2">
                            <input autoFocus value={reason} onChange={(ev) => setReason(ev.target.value)}
                                   placeholder="What's wrong with it? They'll read this."
                                   className="min-w-[14rem] flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm" />
                            <button type="button" disabled={!reason.trim() || busy !== null}
                                    onClick={() => run(`rej-${e.id}`, () => rejectItem(sheet.id, e.id, reason), () => setRejecting(null))}
                                    className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">
                              Reject entry
                            </button>
                            <button type="button" onClick={() => setRejecting(null)}
                                    className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </section>

      {reviewing && sheet.entries.length > 0 && (
        <p className="flex items-start gap-2 rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
          Reject only the entries that are wrong, then approve. Everything you didn&apos;t reject is approved; if you rejected
          anything, the timesheet goes back with just those entries to fix.
        </p>
      )}
    </div>
  );
}
