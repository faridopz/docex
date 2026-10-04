/**
 * Projects & grants — client for api/project_routes.py.
 * Every figure is computed by the server from the records behind it.
 */
import { apiFetch } from "@/lib/session";
import { downloadNamed } from "@/lib/requisitionApi";

export type BudgetLineIn = { code: string; label: string; amount: number };
export type PlannedStaff = { name: string; staff_id?: string; role?: string; percent: number };

export type Agreement = {
  id: string;
  donor: string;
  project_code: string;
  title: string;
  value: number;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  status: "active" | "closed" | "suspended";
  budget_lines: BudgetLineIn[];
  staff: PlannedStaff[];
};

export type LineFigures = {
  code: string;
  label: string;
  budget: number;
  paid: number;
  committed: number;
  remaining: number | null;
};

export type ProjectFigures = {
  agreement_id: string;
  project_code: string;
  donor: string;
  title: string;
  currency: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  budget: number;
  paid: number;
  salary: number;
  committed: number;
  remaining: number;
  used_percent: number | null;
  lines: LineFigures[];
  payments_count: number;
  open_requests_count: number;
  other_currency: string[];
};

export type ProjectPayment = {
  transaction_id: string;
  requisition_id: string;
  requisition_ref: string;
  paid_at: string;
  payee: string;
  category: string;
  amount: number;
  currency: string;
  voucher_number: string;
  bank_reference: string;
  exceptions: number;
};

export type ProjectException = {
  requisition_ref: string;
  paid_at: string;
  payee: string;
  amount: number;
  check: string;
  message: string;
  reason: string;
  released_by: string;
  authority: string;
};

export type ApprovedTime = {
  timesheet_id: string;
  staff_id: string;
  staff_name: string;
  period: string;
  hours: number;
  total_hours: number;
  share_percent: number;
  approved_by: string;
  approved_at: string;
};

export type SalaryRow = {
  period: string;
  staff_id: string;
  name: string;
  percent: number;
  cost: number;
  basis: "timesheet" | "budget" | "none";
};

export type ProjectDetail = {
  agreement: Agreement;
  figures: ProjectFigures;
  payments: ProjectPayment[];
  exceptions: ProjectException[];
  approved_time: ApprovedTime[];
  salary: SalaryRow[];
  can_edit: boolean;
};

export type ProjectInput = Partial<Omit<Agreement, "id">>;

export async function listProjects(): Promise<{ projects: ProjectFigures[]; can_edit: boolean }> {
  return apiFetch("/projects");
}

export async function getProject(code: string): Promise<ProjectDetail> {
  return apiFetch(`/projects/${encodeURIComponent(code)}`);
}

export async function createProject(body: ProjectInput): Promise<{ agreement: Agreement }> {
  return apiFetch("/projects", { method: "POST", body: JSON.stringify(body) });
}

export async function updateProject(code: string, body: ProjectInput): Promise<{ agreement: Agreement }> {
  return apiFetch(`/projects/${encodeURIComponent(code)}`, { method: "PUT", body: JSON.stringify(body) });
}

/** Download the donor report PDF for a date range (either end may be blank). */
export async function downloadDonorReport(code: string, from: string, to: string): Promise<void> {
  const qs = new URLSearchParams();
  if (from) qs.set("date_from", from);
  if (to) qs.set("date_to", to);
  const { blob, filename } = await downloadNamed(
    `/projects/${encodeURIComponent(code)}/report.pdf?${qs}`, `${code}-donor-report.pdf`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export type ProjectLookup =
  | { found: false }
  | { found: true; project_code: string; donor: string; title: string; status: string;
      budget_lines: { code: string; label: string }[] };

/** Names only, no money — for the request form. Null when the feature is off. */
export async function lookupProject(code: string): Promise<ProjectLookup | null> {
  try {
    return await apiFetch(`/projects/lookup/${encodeURIComponent(code)}`);
  } catch {
    return null;
  }
}
