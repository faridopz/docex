/**
 * Timesheet API client.
 *
 * Writes are multipart, matching the Form(...) routes. Entries travel as a
 * JSON string in a form field, which is how the backend takes them.
 */
import { apiFetch } from "@/lib/session";
import type {
  PeriodSummary,
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
