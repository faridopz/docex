"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  LayoutList,
  Loader2,
  Lock,
  Plus,
  Send,
  Trash2,
  Undo2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { TimesheetEntries } from "@/components/erp/TimesheetEntries";
import { useAuth } from "@/lib/auth";
import { getDocumentPermissions } from "@/lib/requisitionApi";
import type { MyProject } from "@/types/timesheet";
import {
  approveTimesheet,
  fillFromPlan,
  myProjects,
  reopenTimesheet,
  getPolicy,
  getTimesheet,
  returnTimesheet,
  saveEntries,
  submitTimesheet,
} from "@/lib/timesheetApi";
import {
  clearHours,
  type Column,
  columnsFor,
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
  type Span,
  spanOf,
} from "@/lib/timesheetGrid";
import type { EntryMode } from "@/lib/timesheetGrid";
import type { Timesheet } from "@/types/timesheet";

/**
 * One month's timesheet.
 *
 * Two ways to look at the same entries. "Entries" (the default since WO-77)
 * is a list: add a line, see each line's review status. "Month view" is the
 * original grid — projects down, days across — for people who prefer it; it
 * goes read-only once a supervisor has approved any entry, because the grid
 * saves the whole month at once and approved lines are evidence.
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
  const [view, setView] = useState<"entries" | "month">("entries");
  const [grid, setGrid] = useState<Grid>({});
  const [mode, setMode] = useState<EntryMode>("halfday");
  const [span, setSpan] = useState<Span>("day");
  const [allowedSpans, setAllowedSpans] = useState<Span[]>(["day", "week", "month"]);
  const [standardHours, setStandardHours] = useState(160);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [newProject, setNewProject] = useState("");
  const { user } = useAuth();
  const [mine, setMine] = useState<MyProject[]>([]);
  const [handlesMoney, setHandlesMoney] = useState(false);
  useEffect(() => {
    myProjects().then((r) => setMine(r.projects)).catch(() => setMine([]));
    getDocumentPermissions().then((p) => setHandlesMoney(Boolean(p.handles_money))).catch(() => {});
  }, []);
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
      // A month recorded by week or month total only makes sense on the grid.
      if (t.span === "week" || t.span === "month") setView("month");
      const g = entriesToGrid(t.entries);
      setSpan(spanOf(t.entries));
      setGrid(g);
      savedGrid.current = JSON.stringify(g);
      setDirty(false);
      if (policy) {
        setStandardHours(policy.standard_hours_per_period);
        if (policy.allowed_spans?.length) setAllowedSpans(policy.allowed_spans);
      }
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
  const columns: Column[] = useMemo(
    () => (sheet ? columnsFor(sheet.period, span) : []),
    [sheet, span],
  );
  const projects = useMemo(() => Object.keys(grid).sort(), [grid]);
  const allocation = useMemo(() => previewAllocation(grid), [grid]);
  const missing = useMemo(
    () => (span === "day" ? missingWorkingDays(grid, days) : []),
    [grid, days, span],
  );
  const total = gridTotal(grid);

  const editable = sheet?.status === "draft" || sheet?.status === "returned";
  const isOwner = (sheet?.staff_id ?? "").toLowerCase() === (user?.email ?? "").toLowerCase();
  const rejectedCount = sheet?.entry_counts?.rejected ?? 0;

  /** The server's copy after an entry changes: the grid follows it. */
  function applySheet(t: Timesheet) {
    setSheet(t);
    const g = entriesToGrid(t.entries);
    setGrid(g);
    savedGrid.current = JSON.stringify(g);
    setDirty(false);
  }

  async function switchView(next: "entries" | "month") {
    if (next === view) return;
    // Leaving the grid with unsaved edits: save them rather than lose them.
    if (view === "month" && dirty && !(await save())) return;
    setView(next);
  }

  function update(next: Grid) {
    setGrid(next);
    setDirty(JSON.stringify(next) !== savedGrid.current);
  }

  async function save(): Promise<Timesheet | null> {
    if (!sheet) return null;
    setBusy("save");
    setError(null);
    try {
      const updated = await saveEntries(sheet.id, gridToEntries(grid, {}, span));
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
      // The server's copy is the truth after any action: refresh the grid
      // from it too (filling the month changes the entries).
      const t = await fn();
      setSheet(t);
      const g = entriesToGrid(t.entries);
      setGrid(g);
      savedGrid.current = JSON.stringify(g);
      setDirty(false);
      setReturning(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  function switchSpan(next: Span) {
    if (next === span) return;
    if (gridTotal(grid) > 0 && !window.confirm(
      "Switching clears the hours entered so far (the project rows stay). A month is recorded one way, so nothing is counted twice. Switch?",
    )) return;
    setSpan(next);
    update(clearHours(grid));
    setDirty(true);
  }

  async function fillMonth() {
    if (!sheet) return;
    const saved = dirty ? await save() : sheet;
    if (!saved) return;
    await act(() => fillFromPlan(sheet.id), "fill");
  }

  async function reopen() {
    if (!sheet) return;
    await act(() => reopenTimesheet(sheet.id, 5), "reopen");
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

  const gridEditable = editable && !(sheet.entry_counts?.approved ?? 0);
  const blocking = sheet.issues.filter((i) => i.blocking);
  const warnings = sheet.issues.filter((i) => !i.blocking);

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-5 pb-24 py-6 sm:px-6 lg:px-8">
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

        <div className="inline-flex rounded-lg border border-gray-300 bg-white p-0.5">
          {([["entries", "Entries", LayoutList], ["month", "Month view", CalendarDays]] as const).map(([key, label, Icon]) => (
            <button key={key} type="button" onClick={() => switchView(key)}
                    className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium ${
                      view === key ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-50"}`}>
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
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

        {editable && sheet.locked && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <Lock className="h-4 w-4 shrink-0" />
            <span className="flex-1">
              This month closed for changes on {sheet.lock_date}. Ask Finance to reopen it if something needs correcting.
            </span>
            {handlesMoney && (
              <button type="button" onClick={reopen} disabled={busy !== null}
                      className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100">
                Reopen for 5 days
              </button>
            )}
          </div>
        )}

        {!editable && (
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
            <Lock className="h-4 w-4 shrink-0" />
            {sheet.status === "submitted" && sheet.stage === "second"
              ? `Signed by ${sheet.supervisor_approved_by}; now waiting for the second signature.`
              : sheet.status === "submitted"
              ? "Submitted and waiting for a supervisor. It cannot be edited while it is with them."
              : sheet.status === "approved"
                ? "Approved. These hours are now evidence for what each grant is charged."
                : "Used in a payroll run, so it is frozen — changing it would break the link between what was paid and what was worked."}
          </div>
        )}

        {view === "month" && gridEditable === false && editable && (
          <p className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
            Some entries are already approved, so the month view is read-only. Change the other entries in the Entries view.
          </p>
        )}

        {view === "month" && (
        <>
        {gridEditable && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
            {allowedSpans.length > 1 && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-gray-500">Record by</span>
                <div className="inline-flex rounded-lg border border-gray-300 p-0.5">
                  {(["day", "week", "month"] as Span[])
                    .filter((sp) => allowedSpans.includes(sp))
                    .map((sp) => (
                      <button
                        className={`rounded-md px-3 py-1 text-sm font-medium ${
                          span === sp ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-50"
                        }`}
                        key={sp}
                        onClick={() => switchSpan(sp)}
                        type="button"
                      >
                        {sp === "day" ? "Day" : sp === "week" ? "Week" : "Month"}
                      </button>
                    ))}
                </div>
              </div>
            )}
            {span === "day" && (
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
            )}
            <p className="text-xs text-gray-500">
              {span === "week"
                ? "Type the hours you worked on each project in each week."
                : span === "month"
                  ? "Type the hours you worked on each project this month."
                  : mode === "halfday"
                    ? `Click a cell: empty → ½ day → full day. A full day is ${perDay}h.`
                    : "Type hours into any cell."}
            </p>
            {span === "day" && sheet.staff_id.toLowerCase() === (user?.email ?? "").toLowerCase()
              && mine.some((p) => p.planned_percent > 0) && (
              <button type="button" onClick={fillMonth} disabled={busy !== null}
                      title="Fills empty working days up to today from your planned split; days you've recorded are left alone"
                      className="rounded-md border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100">
                {busy === "fill" ? "Filling…" : "Fill my month from my usual split"}
              </button>
            )}
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
                {columns.map((d) => (
                  <th
                    className={`${span === "day" ? "w-9" : "min-w-[5.5rem]"} px-0 py-1 text-center text-[11px] font-medium ${
                      d.isWeekend ? "bg-gray-100 text-gray-400" : "text-gray-500"
                    }`}
                    key={d.key}
                  >
                    <div>{d.top}</div>
                    <div className="font-semibold text-gray-700">{d.bottom}</div>
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
                      {gridEditable && (
                        <>
                          <button
                            className="text-gray-300 hover:text-red-600"
                            onClick={() => update(removeProject(grid, project))}
                            title="Remove this row"
                            type="button"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                          {span === "day" && <button
                            className="ml-auto shrink-0 text-[11px] text-blue-600 hover:underline"
                            onClick={() =>
                              update(fillWorkingDays(grid, project, days, perDay))
                            }
                            title="Fill every empty working day with a full day"
                            type="button"
                          >
                            fill
                          </button>}
                        </>
                      )}
                    </div>
                  </td>
                  {columns.map((d) => {
                    const hours = grid[project]?.[d.key] ?? 0;
                    return (
                      <td
                        className={`p-0 text-center ${d.isWeekend ? "bg-gray-50" : ""}`}
                        key={d.key}
                      >
                        {span === "day" && mode === "halfday" ? (
                          <button
                            className={`h-8 w-full text-xs font-semibold ${
                              hours
                                ? "bg-blue-50 text-blue-800 hover:bg-blue-100"
                                : "text-gray-300 hover:bg-gray-50"
                            } ${gridEditable ? "" : "cursor-default"}`}
                            disabled={!gridEditable}
                            onClick={() =>
                              update(
                                setCell(grid, project, d.key,
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
                            disabled={!gridEditable}
                            inputMode="decimal"
                            onChange={(e) =>
                              update(
                                setCell(grid, project, d.key,
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
                  {span === "day" ? "Day total" : "Total"}
                </td>
                {columns.map((d) => {
                  const t = dayTotal(grid, d.key);
                  const empty = span === "day" && !t && !d.isWeekend;
                  return (
                    <td
                      className={`py-1.5 text-center font-medium ${
                        empty
                          ? "bg-amber-50 text-amber-600"
                          : t > d.days * 24
                            ? "bg-red-50 text-red-700"
                            : "text-gray-600"
                      }`}
                      key={d.key}
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

        {gridEditable && (
          <div className="flex flex-wrap items-center gap-2">
            {mine.filter((p) => !grid[p.project_code]).map((p) => (
              <button key={p.project_code} type="button"
                      onClick={() => update({ ...grid, [p.project_code]: {} })}
                      title={[p.donor, p.title].filter(Boolean).join(" · ")}
                      className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100">
                + {p.project_code}
              </button>
            ))}
            <input
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
              onChange={(e) => setNewProject(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addProject()}
              placeholder={mine.length ? "Another project code" : "Add a project code, e.g. GF-2026-TB"}
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

        </>
        )}

        {view === "entries" && (
          <TimesheetEntries sheet={sheet} mine={mine} isOwner={isOwner} editable={editable && !sheet.locked}
                            onChange={applySheet} />
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
          {editable && isOwner && (
            <>
              {view === "month" && gridEditable && <button
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                disabled={!dirty || busy !== null}
                onClick={save}
                type="button"
              >
                {busy === "save" ? "Saving…" : dirty ? "Save" : "Saved"}
              </button>}
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

          {sheet.status === "submitted" && !isOwner && (
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
                {rejectedCount > 0
                  ? `Approve the rest · send back ${rejectedCount} rejected`
                  : "Approve"}
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                onClick={() => setReturning((v) => !v)}
                type="button"
              >
                <Undo2 className="h-4 w-4" />
                Send back
              </button>
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
