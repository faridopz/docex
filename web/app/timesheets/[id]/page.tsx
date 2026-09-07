"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Lock,
  Plus,
  Send,
  Trash2,
  Undo2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  approveTimesheet,
  getPolicy,
  getTimesheet,
  returnTimesheet,
  saveEntries,
  submitTimesheet,
} from "@/lib/timesheetApi";
import {
  cycleHalfDay,
  DayInfo,
  daysInPeriod,
  dayTotal,
  entriesToGrid,
  fillWorkingDays,
  Grid,
  gridToEntries,
  gridTotal,
  halfDayLabel,
  hoursPerDay,
  missingWorkingDays,
  NON_PROJECT,
  previewAllocation,
  projectTotal,
  removeProject,
  setCell,
} from "@/lib/timesheetGrid";
import type { EntryMode } from "@/lib/timesheetGrid";
import type { Timesheet } from "@/types/timesheet";

/**
 * The timesheet grid.
 *
 * Projects down, days across, one screen for the month. See lib/timesheetGrid
 * for why this shape rather than a list of entries.
 *
 * The design rule throughout: the person filling this in should never have to
 * ask "have I finished?". Missing working days are counted at the top, the
 * running split is beside the grid, and Submit refuses while anything is
 * blocking — with the reason stated, not just the button greyed out.
 */
export default function TimesheetDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;

  const [sheet, setSheet] = useState<Timesheet | null>(null);
  const [grid, setGrid] = useState<Grid>({});
  const [mode, setMode] = useState<EntryMode>("halfday");
  const [standardHours, setStandardHours] = useState(160);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [newProject, setNewProject] = useState("");
  const [returning, setReturning] = useState(false);
  const [returnReason, setReturnReason] = useState("");
  const savedGrid = useRef<string>("");

  const load = useCallback(async () => {
    try {
      const [t, policy] = await Promise.all([
        getTimesheet(id),
        getPolicy().catch(() => null),
      ]);
      setSheet(t);
      const g = entriesToGrid(t.entries);
      setGrid(g);
      savedGrid.current = JSON.stringify(g);
      setDirty(false);
      if (policy) setStandardHours(policy.standard_hours_per_period);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this timesheet.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const days: DayInfo[] = useMemo(
    () => (sheet ? daysInPeriod(sheet.period) : []),
    [sheet],
  );
  const perDay = useMemo(
    () => hoursPerDay(standardHours, days),
    [standardHours, days],
  );
  const projects = useMemo(() => Object.keys(grid).sort(), [grid]);
  const allocation = useMemo(() => previewAllocation(grid), [grid]);
  const missing = useMemo(() => missingWorkingDays(grid, days), [grid, days]);
  const total = gridTotal(grid);

  const editable = sheet?.status === "draft" || sheet?.status === "returned";

  function update(next: Grid) {
    setGrid(next);
    setDirty(JSON.stringify(next) !== savedGrid.current);
  }

  async function save(): Promise<Timesheet | null> {
    if (!sheet) return null;
    setBusy("save");
    setError(null);
    try {
      const updated = await saveEntries(sheet.id, gridToEntries(grid));
      setSheet(updated);
      savedGrid.current = JSON.stringify(grid);
      setDirty(false);
      return updated;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function saveAndSubmit() {
    if (!sheet) return;
    // Always save first: submitting a sheet that still holds unsaved edits
    // would validate the wrong thing and approve the wrong hours.
    const saved = dirty ? await save() : sheet;
    if (!saved) return;
    setBusy("submit");
    setError(null);
    try {
      setSheet(await submitTimesheet(sheet.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit.");
    } finally {
      setBusy(null);
    }
  }

  async function act(fn: () => Promise<Timesheet>, key: string) {
    setBusy(key);
    setError(null);
    try {
      setSheet(await fn());
      setReturning(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  function addProject() {
    const code = newProject.trim().toUpperCase();
    if (!code || grid[code]) return;
    update({ ...grid, [code]: {} });
    setNewProject("");
  }

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

  if (!sheet) {
    return (
      <AppShell>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error ?? "Timesheet not found."}
        </div>
      </AppShell>
    );
  }

  const blocking = sheet.issues.filter((i) => i.blocking);
  const warnings = sheet.issues.filter((i) => !i.blocking);

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-5 pb-24">
        <div>
          <Link
            className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
            href="/timesheets"
          >
            <ArrowLeft className="h-4 w-4" />
            Timesheets
          </Link>
          <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">
                {new Date(
                  Number(sheet.period.split("-")[0]),
                  Number(sheet.period.split("-")[1]) - 1,
                  1,
                ).toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </h1>
              <p className="text-sm text-gray-600">
                {sheet.staff_name || sheet.staff_id}
                {sheet.approved_by && ` · approved by ${sheet.approved_by}`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-semibold text-gray-900">{total}</p>
              <p className="text-xs text-gray-500">hours recorded</p>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        )}

        {sheet.status === "returned" && sheet.returned_reason && (
          <div className="rounded-lg border border-orange-200 bg-orange-50 p-4 text-sm text-orange-900">
            <span className="font-medium">Sent back:</span> {sheet.returned_reason}
          </div>
        )}

        {!editable && (
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
            <Lock className="h-4 w-4 shrink-0" />
            {sheet.status === "submitted"
              ? "Submitted and waiting for a supervisor. It cannot be edited while it is with them."
              : sheet.status === "approved"
                ? "Approved. These hours are now evidence for what each grant is charged."
                : "Used in a payroll run, so it is frozen — changing it would break the link between what was paid and what was worked."}
          </div>
        )}

        {editable && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
            <div className="inline-flex rounded-lg border border-gray-300 p-0.5">
              {(["halfday", "hours"] as EntryMode[]).map((m) => (
                <button
                  className={`rounded-md px-3 py-1 text-sm font-medium ${
                    mode === m
                      ? "bg-blue-600 text-white"
                      : "text-gray-600 hover:bg-gray-50"
                  }`}
                  key={m}
                  onClick={() => setMode(m)}
                  type="button"
                >
                  {m === "halfday" ? "Half days" : "Hours"}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500">
              {mode === "halfday"
                ? `Click a cell: empty → ½ day → full day. A full day is ${perDay}h.`
                : "Type hours into any cell."}
            </p>
            {missing.length > 0 && (
              <span className="ml-auto text-xs font-medium text-amber-700">
                {missing.length} working day{missing.length === 1 ? "" : "s"} empty
              </span>
            )}
          </div>
        )}

        {/* ── the grid ─────────────────────────────────────────────────── */}
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="sticky left-0 z-10 min-w-[10rem] bg-gray-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Project
                </th>
                {days.map((d) => (
                  <th
                    className={`w-9 px-0 py-1 text-center text-[11px] font-medium ${
                      d.isWeekend ? "bg-gray-100 text-gray-400" : "text-gray-500"
                    }`}
                    key={d.date}
                  >
                    <div>{d.weekday[0]}</div>
                    <div className="font-semibold text-gray-700">{d.day}</div>
                  </th>
                ))}
                <th className="w-16 px-2 py-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr className="border-b border-gray-100" key={project}>
                  <td className="sticky left-0 z-10 bg-white px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <span
                        className={`truncate font-medium ${
                          project === NON_PROJECT ? "text-gray-500" : "text-gray-900"
                        }`}
                      >
                        {project === NON_PROJECT ? "Leave / admin" : project}
                      </span>
                      {editable && (
                        <>
                          <button
                            className="text-gray-300 hover:text-red-600"
                            onClick={() => update(removeProject(grid, project))}
                            title="Remove this row"
                            type="button"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                          <button
                            className="ml-auto shrink-0 text-[11px] text-blue-600 hover:underline"
                            onClick={() =>
                              update(fillWorkingDays(grid, project, days, perDay))
                            }
                            title="Fill every empty working day with a full day"
                            type="button"
                          >
                            fill
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                  {days.map((d) => {
                    const hours = grid[project]?.[d.date] ?? 0;
                    return (
                      <td
                        className={`p-0 text-center ${d.isWeekend ? "bg-gray-50" : ""}`}
                        key={d.date}
                      >
                        {mode === "halfday" ? (
                          <button
                            className={`h-8 w-full text-xs font-semibold ${
                              hours
                                ? "bg-blue-50 text-blue-800 hover:bg-blue-100"
                                : "text-gray-300 hover:bg-gray-50"
                            } ${editable ? "" : "cursor-default"}`}
                            disabled={!editable}
                            onClick={() =>
                              update(
                                setCell(grid, project, d.date,
                                  cycleHalfDay(hours, perDay)),
                              )
                            }
                            type="button"
                          >
                            {halfDayLabel(hours, perDay) || "·"}
                          </button>
                        ) : (
                          <input
                            className="h-8 w-full border-0 bg-transparent p-0 text-center text-xs focus:bg-blue-50 focus:outline-none disabled:text-gray-600"
                            disabled={!editable}
                            inputMode="decimal"
                            onChange={(e) =>
                              update(
                                setCell(grid, project, d.date,
                                  Number(e.target.value) || 0),
                              )
                            }
                            value={hours || ""}
                          />
                        )}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5 text-right font-medium text-gray-900">
                    {projectTotal(grid, project) || ""}
                  </td>
                </tr>
              ))}

              <tr className="bg-gray-50 text-xs">
                <td className="sticky left-0 z-10 bg-gray-50 px-3 py-1.5 font-semibold uppercase tracking-wide text-gray-500">
                  Day total
                </td>
                {days.map((d) => {
                  const t = dayTotal(grid, d.date);
                  const empty = !t && !d.isWeekend;
                  return (
                    <td
                      className={`py-1.5 text-center font-medium ${
                        empty
                          ? "bg-amber-50 text-amber-600"
                          : t > 24
                            ? "bg-red-50 text-red-700"
                            : "text-gray-600"
                      }`}
                      key={d.date}
                      title={empty ? "No hours recorded on a working day" : undefined}
                    >
                      {t || (empty ? "—" : "")}
                    </td>
                  );
                })}
                <td className="px-2 py-1.5 text-right font-semibold text-gray-900">
                  {total}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {editable && (
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
              onChange={(e) => setNewProject(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addProject()}
              placeholder="Add a project code, e.g. GF-2026-TB"
              value={newProject}
            />
            <button
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
              onClick={addProject}
              type="button"
            >
              <Plus className="h-4 w-4" />
              Add project
            </button>
            {!grid[NON_PROJECT] && (
              <button
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
                onClick={() => update({ ...grid, [NON_PROJECT]: {} })}
                title="Leave, admin and training still have to be recorded"
                type="button"
              >
                + Leave / admin
              </button>
            )}
          </div>
        )}

        {/* ── the split, and what is wrong ─────────────────────────────── */}
        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900">
              What each grant will be charged
            </h2>
            <p className="mt-0.5 text-xs text-gray-500">
              From the hours recorded, not from a budget. Leave and admin are
              excluded.
            </p>
            {Object.keys(allocation).length === 0 ? (
              <p className="mt-3 text-sm text-gray-400">Nothing recorded yet.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {Object.entries(allocation)
                  .sort((a, b) => b[1] - a[1])
                  .map(([code, pct]) => (
                    <li key={code}>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-700">{code}</span>
                        <span className="font-medium text-gray-900">{pct}%</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
                        <div
                          className="h-full rounded-full bg-blue-600"
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900">Checks</h2>
            {blocking.length === 0 && warnings.length === 0 ? (
              <p className="mt-3 flex items-center gap-2 text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                Nothing outstanding.
              </p>
            ) : (
              <ul className="mt-3 space-y-2 text-sm">
                {blocking.map((i) => (
                  <li className="flex items-start gap-2 text-red-700" key={i.code}>
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{i.message}</span>
                  </li>
                ))}
                {warnings.map((i) => (
                  <li className="flex items-start gap-2 text-amber-700" key={i.code}>
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{i.message}</span>
                  </li>
                ))}
              </ul>
            )}
            {dirty && (
              <p className="mt-3 text-xs text-gray-500">
                Checks re-run when you save.
              </p>
            )}
          </section>
        </div>

        {/* ── actions ──────────────────────────────────────────────────── */}
        <div className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t border-gray-200 bg-white/95 py-3 backdrop-blur">
          {editable && (
            <>
              <button
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                disabled={!dirty || busy !== null}
                onClick={save}
                type="button"
              >
                {busy === "save" ? "Saving…" : dirty ? "Save" : "Saved"}
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                disabled={busy !== null || total === 0}
                onClick={saveAndSubmit}
                type="button"
              >
                {busy === "submit" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                Submit for approval
              </button>
              {blocking.length > 0 && (
                <span className="text-xs text-red-700">
                  {blocking.length} problem{blocking.length === 1 ? "" : "s"} must
                  be fixed first.
                </span>
              )}
            </>
          )}

          {sheet.status === "submitted" && (
            <>
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                disabled={busy !== null}
                onClick={() => act(() => approveTimesheet(sheet.id), "approve")}
                type="button"
              >
                {busy === "approve" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Approve
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                onClick={() => setReturning((v) => !v)}
                type="button"
              >
                <Undo2 className="h-4 w-4" />
                Send back
              </button>
              <p className="w-full text-xs text-gray-500">
                You cannot approve your own timesheet — self-approval of effort
                records is a finding auditors look for specifically.
              </p>
            </>
          )}
        </div>

        {returning && (
          <div className="space-y-2 rounded-xl border border-orange-200 bg-orange-50 p-4">
            <p className="text-sm text-orange-900">
              Say what needs fixing. &quot;Fix it&quot; is not feedback, and the
              reason is kept on the record.
            </p>
            <textarea
              className="w-full rounded-lg border border-gray-300 p-2 text-sm"
              onChange={(e) => setReturnReason(e.target.value)}
              placeholder="e.g. The last week of the month is missing."
              rows={2}
              value={returnReason}
            />
            <button
              className="rounded-lg bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
              disabled={!returnReason.trim() || busy !== null}
              onClick={() =>
                act(() => returnTimesheet(sheet.id, returnReason), "return")
              }
              type="button"
            >
              Send it back
            </button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
