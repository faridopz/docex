/**
 * Is this account really in this payee's name? (WO-48)
 * Requires the payee_account_check flag server-side; both calls 404 without it,
 * and the form simply shows nothing.
 */
import { apiFetch } from "@/lib/session";

export interface BankOption {
  code: string;
  name: string;
}

export type AccountCheckStatus =
  | "verified"
  | "warning"
  | "mismatch"
  | "unverifiable"
  | "unknown_bank"
  | "not_configured";

export interface AccountCheck {
  status: AccountCheckStatus;
  /** Masked: last four digits only. */
  account: string;
  bank_name_on_record: string | null;
  message: string;
}

export async function listBanks(): Promise<BankOption[]> {
  const r = await apiFetch<{ banks: BankOption[] }>("/payee-check/banks");
  return r.banks ?? [];
}

export async function checkAccount(body: {
  name: string;
  account_number: string;
  bank: string;
}): Promise<AccountCheck> {
  return apiFetch<AccountCheck>("/payee-check/account", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
