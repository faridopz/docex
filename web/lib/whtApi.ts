/**
 * Withholding tax — the client for /treasury/wht/*.
 *
 * DOCex ships NO rates. An organisation that has not entered its schedule
 * withholds nothing, rather than applying a plausible guess to real invoices.
 * Every type here allows an empty policy for that reason.
 */
import { apiFetch } from "./session";

export type PayeeType = "company" | "individual" | "any";

export type WHTRule = {
  category: string;
  rate_percent: number;
  /** Nigerian rates commonly differ between companies and individuals for the
   *  same service. Applying the company rate to an individual is a real
   *  over-deduction, and the vendor notices before the auditor does. */
  payee_type: PayeeType;
  description: string;
};

export type WHTPolicy = {
  org_id: string;
  enabled: boolean;
  rules: WHTRule[];
  authority_name: string;
  remittance_method: string;
  account_code: string;
  minimum_amount: number;
  updated_at: string | null;
  note?: string;
};

export type WHTResult = {
  applicable: boolean;
  gross: number;
  rate_percent: number;
  withheld: number;
  net: number;
  category: string;
  payee_type: string;
  reason: string;
};

export function getWhtPolicy() {
  return apiFetch<WHTPolicy>("/treasury/wht/policy");
}

export function setWhtPolicy(policy: Partial<WHTPolicy>) {
  return apiFetch<WHTPolicy>("/treasury/wht/policy", {
    method: "PUT",
    body: JSON.stringify(policy),
  });
}

/** What would be withheld from this payment, and why. */
export function previewWht(gross: number, category: string, payeeType: PayeeType = "company") {
  const fd = new FormData();
  fd.append("gross", String(gross));
  fd.append("category", category);
  fd.append("payee_type", payeeType);
  return apiFetch<WHTResult>("/treasury/wht/preview", { method: "POST", body: fd });
}

export function whtLiability(period: string) {
  return apiFetch<{ period: string; total_withheld: number; count: number; lines: unknown[] }>(
    `/treasury/wht/liability?period=${encodeURIComponent(period)}`,
  );
}
