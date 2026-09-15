/**
 * What THIS client's instance has switched on.
 *
 * The engine is shared by every client. What makes one client's system feel
 * like theirs is their profile — which product areas they bought (`modules`)
 * and which capabilities inside them are on (`features`). Both come from
 * `profiles/<client>.json`, applied with org_config.py, and are read here so
 * the navigation only ever offers what that organisation actually has.
 *
 * Hiding a menu item is a courtesy, never a security boundary: the API
 * enforces authorisation on every route that does real work.
 */
import { apiFetch } from "@/lib/session";

export type ModuleKey = "compliance" | "screening" | "knowledge";

export type ClientConfig = {
  modules: ModuleKey[];
  features: Record<string, boolean>;
};

/**
 * Fall back to every module and no features. This is the behaviour an
 * unconfigured instance had before this endpoint existed: nav shows
 * everything, individual capabilities stay off until switched on. Failing
 * open on modules keeps a network blip from emptying someone's navigation
 * mid-session; failing closed on features keeps a blip from advertising a
 * capability the client never bought.
 */
export const DEFAULT_CLIENT_CONFIG: ClientConfig = {
  modules: ["compliance", "screening", "knowledge"],
  features: {},
};

export async function getClientConfig(): Promise<ClientConfig> {
  const cfg = await apiFetch<ClientConfig>("/org/config");
  return {
    modules: Array.isArray(cfg.modules) && cfg.modules.length
      ? cfg.modules
      : DEFAULT_CLIENT_CONFIG.modules,
    features: cfg.features ?? {},
  };
}

/** Admin-only: turn modules/features on or off for this org, live. Either
 * key can be omitted to leave that half unchanged. */
export async function setClientConfig(
  body: { modules?: ModuleKey[]; features?: Record<string, boolean> },
): Promise<ClientConfig> {
  return apiFetch("/org/config", { method: "PUT", body: JSON.stringify(body) });
}

/** Every module/feature name a route in this instance actually gates on —
 * kept in sync with api/org_routes.py's KNOWN_MODULES / KNOWN_FEATURES so
 * the settings screen never invents a toggle for a flag nothing reads, or
 * misses one that exists. */
export const ALL_MODULES: { key: ModuleKey; label: string; desc: string }[] = [
  { key: "compliance", label: "Compliance & Finance", desc: "Requisitions, policy checks, approvals, pipeline, bank verification, attendance." },
  { key: "screening", label: "Screening", desc: "Ask questions across a stack of documents with cited answers." },
  { key: "knowledge", label: "Knowledge", desc: "Ask your document library a question and get a cited answer." },
];

export const ALL_FEATURES: { key: string; label: string; desc: string }[] = [
  { key: "attendance_payments", label: "Attendance payments", desc: "Per-diem/rate-card vouchers for event participants." },
  { key: "withholding_tax", label: "Withholding tax", desc: "Deduct and track statutory tax withheld from vendor payments." },
  { key: "bank_reconciliation", label: "Bank reconciliation", desc: "Match approved payments against the bank statement, both directions." },
  { key: "vendor_register", label: "Vendor register", desc: "Approved-vendor list with bank-account verification." },
  { key: "timesheets", label: "Timesheets", desc: "Daily effort reporting allocated to grants, for payroll cost-sharing." },
  { key: "payroll", label: "Payroll", desc: "Gross-to-net payroll runs allocated to donors and project codes." },
  { key: "advance_retirement", label: "Advance retirement", desc: "Track and escalate unretired travel/cash advances." },
  { key: "accounting_export", label: "Accounting export", desc: "Export the coded payment register and cleaned bank statement." },
  { key: "multi_payee_requisitions", label: "Multi-payee requisitions", desc: "Raise one requisition that pays many people at once — a workshop stipend list or a beneficiary payout run." },
  { key: "requisition_hold", label: "Requisition hold", desc: "Let an approver pause a requisition at its current step, with a written reason, instead of approving/declining/returning it." },
  { key: "requisition_attachments", label: "File attachments", desc: "Attach real files (invoices, memos, receipts) to a requisition, not just a checklist of document labels." },
];

/** True only when the flag is explicitly on. Unknown flag ⇒ off. */
export function hasFeature(cfg: ClientConfig, name: string): boolean {
  return cfg.features[name] === true;
}
