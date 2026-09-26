/**
 * The organisation's bank accounts — which one a payment left from, and
 * which one a statement belongs to. Numbers come back masked, always.
 * Requires the bank_reconciliation flag server-side.
 */
import { apiFetch } from "@/lib/session";

export interface BankAccount {
  id: string;
  code: string;
  name: string;
  label: string;
  bank_name: string;
  /** Masked: last four digits only. */
  account_number: string;
  project_code: string;
  purpose: string;
  active: boolean;
}

export async function listBankAccounts(): Promise<BankAccount[]> {
  const r = await apiFetch<{ accounts: BankAccount[] }>("/treasury/accounts");
  return r.accounts ?? [];
}

export async function addBankAccount(body: {
  code: string;
  name: string;
  account_number: string;
  bank_name: string;
  project_code: string;
}): Promise<BankAccount> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(body)) fd.append(k, v);
  return apiFetch<BankAccount>("/treasury/accounts", { method: "POST", body: fd });
}

export async function closeBankAccount(id: string, reason: string): Promise<BankAccount> {
  const fd = new FormData();
  fd.append("reason", reason);
  return apiFetch<BankAccount>(`/treasury/accounts/${encodeURIComponent(id)}/close`, {
    method: "POST",
    body: fd,
  });
}

/** The account a payment on this project would be paid from, when it is
 * unambiguous: the only account, or the only one carrying the project code.
 * Mirrors bank_accounts.account_for_payment; the server re-decides. */
export function suggestAccount(accounts: BankAccount[], projectCode: string): string {
  const active = accounts.filter((a) => a.active);
  if (active.length === 1) return active[0].id;
  const code = projectCode.trim().toLowerCase();
  if (!code) return "";
  const hits = active.filter((a) => (a.project_code || "").trim().toLowerCase() === code);
  return hits.length === 1 ? hits[0].id : "";
}
