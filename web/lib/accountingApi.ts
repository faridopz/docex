/**
 * QuickBooks handoff — client for api/accounting_routes.py.
 *
 * DOCex sits in front of QuickBooks: this maps DOCex spend categories and
 * project/grant codes to QuickBooks accounts and classes, then exports (1)
 * the coded payment register and (2) a bank statement QuickBooks will
 * actually accept (Nigerian banks aren't connectable to its bank feeds).
 *
 * The export endpoints return plain CSV text, not JSON, so they use a
 * dedicated fetch here rather than the shared apiFetch() JSON helper.
 */
import { getToken } from "@/lib/session";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AccountMap = {
  accounts: Record<string, string>;
  default_account: string;
  classes: Record<string, string>;
  grant_as_customer: boolean;
  bank_account: string;
  date_format: string;
};

export type ExportSummary = {
  period: string;
  payments: number;
  value: number;
  bank_account: string;
  accounts_mapped: number;
  unmapped_categories: string[];
  ready: boolean;
  note: string;
};

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    let message = raw;
    try {
      message = JSON.parse(raw).detail ?? raw;
    } catch {
      /* not JSON — use as-is */
    }
    throw Object.assign(new Error(message || `Request failed (${res.status})`), { status: res.status });
  }
  return res;
}

export async function getAccountMap(): Promise<AccountMap> {
  const res = await authedFetch("/accounting/map");
  return res.json();
}

export async function setAccountMap(map: AccountMap): Promise<AccountMap> {
  const res = await authedFetch("/accounting/map", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(map),
  });
  return res.json();
}

export async function getExportSummary(period: string): Promise<ExportSummary> {
  const res = await authedFetch(`/accounting/summary?period=${encodeURIComponent(period)}`);
  return res.json();
}

/** Downloads the coded payment register directly as a .csv file. */
export async function downloadPaymentRegister(period: string): Promise<void> {
  const res = await authedFetch(`/accounting/export/payments?period=${encodeURIComponent(period)}`);
  const text = await res.text();
  triggerDownload(text, `docex-payments-${period}.csv`);
}

export type BankStatementCleanResult = {
  files: string[];
  file_count: number;
  rows: number;
  columns_used: Record<string, unknown>;
  note: string;
};

export async function cleanBankStatement(
  file: File,
  opts: { fourColumn?: boolean; qboDateFormat?: string } = {},
): Promise<BankStatementCleanResult> {
  const form = new FormData();
  form.append("statement", file);
  if (opts.fourColumn) form.append("four_column", "true");
  if (opts.qboDateFormat) form.append("qbo_date_format", opts.qboDateFormat);
  const res = await authedFetch("/accounting/export/bank-statement", { method: "POST", body: form });
  return res.json();
}

function triggerDownload(text: string, filename: string): void {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export { triggerDownload };
