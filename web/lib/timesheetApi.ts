/**
 * Timesheet API client.
 *
 * Writes are multipart, matching the Form(...) routes. Entries travel as a
 * JSON string in a form field, which is how the backend takes them.
 */
import { apiFetch } from "@/lib/session";
import type {
  MyProject,
  PeriodSummary,
  TeamView,
  Timesheet,
  TimesheetPolicy,
  TimesheetStatus,
  TimesheetSummary,
} from "@/types/timesheet";

export interface EntryInput {
  date: string;
  hours: number;
  project_code: string;
  activity?: string;
  span?: "day" | "week" | "month";
}

function form(fields: Record<string, string | number | undefined>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined) continue;
    fd.append(k, String(v));
  }
  return fd;
}

export async function listTimesheets(opts: {
  period?: string;
  staffId?: string;
  status?: TimesheetStatus;
} = {}): Promise<TimesheetSummary[]> {
  const qs = new URLSearchParams();
  if (opts.period) qs.set("period", opts.period);
  if (opts.staffId) qs.set("staff_id", opts.staffId);
  if (opts.status) qs.set("status", opts.status);
  const suffix = qs.toString() ? `?${qs}` : "";
  const r = await apiFetch<{ timesheets: TimesheetSummary[] }>(`/timesheets${suffix}`);
  return r.timesheets ?? [];
}

export async function myTimesheets(period?: string): Promise<TimesheetSummary[]> {
  const qs = period ? `?period=${encodeURIComponent(period)}` : "";
  const r = await apiFetch<{ timesheets: TimesheetSummary[] }>(`/timesheets/mine${qs}`);
  return r.timesheets ?? [];
}

/** Submitted sheets waiting on a supervisor — never includes your own. */
export async function pendingApproval(): Promise<TimesheetSummary[]> {
  const r = await apiFetch<{ timesheets: TimesheetSummary[] }>("/timesheets/pending");
  return r.timesheets ?? [];
}

export function periodSummary(period: string): Promise<PeriodSummary> {
  return apiFetch<PeriodSummary>(
    `/timesheets/summary?period=${encodeURIComponent(period)}`);
}

export function getPolicy(): Promise<TimesheetPolicy> {
  return apiFetch<TimesheetPolicy>("/timesheets/policy");
}

export function getTimesheet(id: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}`);
}

export function createTimesheet(opts: {
  period: string;
  staffId?: string;
  staffName?: string;
  office?: string;
  entries?: EntryInput[];
}): Promise<Timesheet> {
  return apiFetch<Timesheet>("/timesheets", {
    method: "POST",
    body: form({
      period: opts.period,
      staff_id: opts.staffId,
      staff_name: opts.staffName,
      office: opts.office,
      entries: JSON.stringify(opts.entries ?? []),
    }),
  });
}

/** Replace the whole grid. The backend validates and returns fresh issues. */
export function saveEntries(id: string, entries: EntryInput[]): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/entries`, {
    method: "PUT",
    body: form({ entries: JSON.stringify(entries) }),
  });
}

export function submitTimesheet(id: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/submit`, {
    method: "POST",
  });
}

export function approveTimesheet(id: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/approve`, {
    method: "POST",
  });
}

export function returnTimesheet(id: string, reason: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/return`, {
    method: "POST",
    body: form({ reason }),
  });
}

// ─── the quick paths ────────────────────────────────────────────────────────

export function myProjects(): Promise<{ projects: MyProject[]; non_project: string; hours_per_day: number }> {
  return apiFetch("/timesheets/my-projects");
}

/** Log one day on one project: "half" or "full" day, or a number of hours. */
export function quickLog(opts: {
  projectCode: string; date?: string; portion?: "half" | "full"; hours?: number; activity?: string;
}): Promise<Timesheet> {
  return apiFetch<Timesheet>("/timesheets/quick-log", {
    method: "POST",
    body: form({
      project_code: opts.projectCode,
      date: opts.date,
      portion: opts.portion,
      hours: opts.hours,
      activity: opts.activity,
    }),
  });
}

export function fillFromPlan(id: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/fill-from-plan`, { method: "POST" });
}

export function reopenTimesheet(id: string, days = 5): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/timesheets/${encodeURIComponent(id)}/reopen`, {
    method: "POST",
    body: form({ days }),
  });
}

export function remindOutstanding(period: string): Promise<{ reminded: number; emailed: number; people: string[] }> {
  return apiFetch("/timesheets/remind", { method: "POST", body: form({ period }) });
}

export function savePolicy(policy: Partial<TimesheetPolicy>): Promise<TimesheetPolicy> {
  return apiFetch<TimesheetPolicy>("/timesheets/policy", { method: "PUT", body: JSON.stringify(policy) });
}

// ─── one entry at a time ────────────────────────────────────────────────────

export interface ItemInput {
  date: string;
  projectCode: string;
  hours: number;
  activity?: string;
  overtime?: boolean;
}

function itemForm(i: ItemInput): FormData {
  return form({
    date: i.date,
    project_code: i.projectCode,
    hours: i.hours,
    activity: i.activity ?? "",
    overtime: i.overtime ? "true" : "false",
  });
}

const sheetPath = (id: string) => `/timesheets/${encodeURIComponent(id)}`;

export function addItem(id: string, item: ItemInput): Promise<Timesheet> {
  return apiFetch<Timesheet>(`${sheetPath(id)}/items`, { method: "POST", body: itemForm(item) });
}

export function updateItem(id: string, entryId: string, item: ItemInput): Promise<Timesheet> {
  return apiFetch<Timesheet>(`${sheetPath(id)}/items/${encodeURIComponent(entryId)}`, {
    method: "PUT",
    body: itemForm(item),
  });
}

export function removeItem(id: string, entryId: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`${sheetPath(id)}/items/${encodeURIComponent(entryId)}`, { method: "DELETE" });
}

export function rejectItem(id: string, entryId: string, reason: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`${sheetPath(id)}/items/${encodeURIComponent(entryId)}/reject`, {
    method: "POST",
    body: form({ reason }),
  });
}

export function clearItem(id: string, entryId: string): Promise<Timesheet> {
  return apiFetch<Timesheet>(`${sheetPath(id)}/items/${encodeURIComponent(entryId)}/clear`, { method: "POST" });
}

export function teamView(period: string): Promise<TeamView> {
  return apiFetch<TeamView>(`/timesheets/team?period=${encodeURIComponent(period)}`);
}
