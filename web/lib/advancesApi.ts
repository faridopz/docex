/**
 * Advances: money given ahead of spending, retired against what was spent.
 * Requires the advance_retirement flag server-side (404 without it).
 * Staff get their own advances only; Finance gets everyone's.
 */
import { apiFetch } from "@/lib/session";

export interface AgingRow {
  id: string;
  ref: string;
  staff_id: string;
  staff_name: string;
  department: string;
  amount: number;
  currency: string;
  purpose: string;
  project_code: string;
  issued_at: string;
  due_at: string;
  /** Negative = days left; 0 or more = days late. */
  days_overdue: number;
  status: string;
  escalation: number;
  escalation_name: string;
  consequence: string;
}

export interface Aging {
  as_at: string;
  configured: boolean;
  outstanding: number;
  outstanding_value: number;
  overdue: number;
  overdue_value: number;
  blocked_staff: string[];
  blocked_projects: string[];
  rows: AgingRow[];
  /** True for Finance and admins; false means the list is the viewer's own. */
  sees_everyone: boolean;
}

export interface AdvancePolicy {
  enabled: boolean;
  open_for_categories: string[];
  activity_end_categories: string[];
}

export async function getAging(): Promise<Aging> {
  return apiFetch<Aging>("/advances/aging");
}

export async function getAdvancePolicy(): Promise<AdvancePolicy> {
  return apiFetch<AdvancePolicy>("/advances/policy");
}

function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.append(k, v);
  return f;
}

export async function retireAdvance(id: string, spent: number, note = ""): Promise<void> {
  await apiFetch(`/advances/${id}/retire`, { method: "POST", body: form({ spent: String(spent), note }) });
}

export async function recoverAdvance(id: string, reason: string): Promise<void> {
  await apiFetch(`/advances/${id}/recover`, { method: "POST", body: form({ reason }) });
}

export async function writeOffAdvance(id: string, reason: string): Promise<void> {
  await apiFetch(`/advances/${id}/write-off`, { method: "POST", body: form({ reason }) });
}
