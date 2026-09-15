/**
 * Types for the universal requisition flow (backend: requisitions.py).
 *
 * These mirror the serialisers in api/requisition_routes.py exactly. Where the
 * backend narrows a value to a fixed set (status, check result, decision) we
 * use a union rather than `string`, so a typo in a comparison is a build error
 * instead of a silently-false condition on a payments screen.
 */

export type ReqStatus =
  | "draft"
  | "submitted"
  | "in_review"
  | "on_hold"
  | "approved"
  | "paid"
  | "declined"
  | "returned";

export type CheckResult = "pass" | "warning" | "fail";

export type Decision = "approved" | "declined" | "returned";

/** One deterministic policy check. Code owns the number; this is the verdict. */
export interface PolicyCheck {
  code: string;
  name: string;
  result: CheckResult;
  policy_value: string | null;
  actual_value: string | null;
  message: string;
  /** True when an approver released a FAIL. Never true without a reason. */
  overridden: boolean;
  override_by: string | null;
  override_reason: string | null;
  override_authority: string | null;
}

/** A signed decision at one step of the approval chain. */
export interface Approval {
  step: string;
  department: string;
  actor: string;
  decision: Decision;
  notes: string;
  at: string;
  /** Policy check codes this decision released. */
  overrides: string[];
  /** Truncated digest — proof a signature exists, not the signature itself. */
  signature: string;
}

/** One line of the hash-chained, append-only audit log. */
export interface AuditEntry {
  seq: number;
  at: string;
  actor: string;
  department: string;
  event: string;
  detail: string;
}

export interface WorkflowStep {
  key: string;
  label: string;
  department: string;
  /** This step only engages at or above this amount. */
  min_amount: number;
  can_override: boolean;
  override_limit: number | null;
}

/** A department copied on a requisition once its amount crosses a threshold
 * — informed, never asked to act. Separate from WorkflowStep on purpose:
 * decide() only ever checks a step's department, so a CC rule can never
 * grant approval authority. */
export interface CCRule {
  min_amount: number;
  department: string;
  label: string;
  /** Named individuals (by email) copied in addition to `department`, which
   * may be left blank for a rule that only names people. */
  emails: string[];
}

export interface RequisitionWorkflow {
  org_id: string;
  steps: WorkflowStep[];
  currency: string;
  max_amount: number | null;
  allowed_categories: string[];
  forbidden_vendors: string[];
  approved_vendors: string[];
  required_documents: string[];
  /** Per-category document checklist. A category with no entry here falls
   * back to required_documents (the org-wide list). Keyed by category name. */
  documents_by_category: Record<string, string[]>;
  duplicate_window_days: number;
  /** Ceiling on payees in one multi-payee requisition (a workshop stipend
   * list, a beneficiary payout run). */
  max_payees: number;
  cc_rules: CCRule[];
  updated_at: string | null;
}

/** One line of a multi-payee requisition. */
export interface Payee {
  name: string;
  account_number: string;
  bank_name: string;
  amount: number;
  purpose: string;
  tin: string;
  phone_or_email: string;
  payee_type: "staff" | "vendor" | "beneficiary";
}

/** List-row shape — enough to triage a queue without opening anything. */
export interface RequisitionSummary {
  id: string;
  ref: string;
  vendor_name: string;
  amount: number;
  currency: string;
  category: string;
  project_code: string;
  grant_code: string | null;
  department: string;
  submitted_by: string;
  submitted_at: string;
  status: ReqStatus;
  current_step: string | null;
  blocking_count: number;
  warning_count: number;
  updated_at: string | null;
}

export interface Requisition extends RequisitionSummary {
  vendor_account: string;
  description: string;
  receipt_ids: string[];
  documents: string[];
  /** Populated for a multi-payee batch; empty for an ordinary single-vendor
   * requisition. When non-empty, `amount` above is the sum of these. */
  payees: Payee[];
  /** Set only while status is "on_hold"; null the rest of the time. The
   * hold/release history itself lives in audit_log regardless. */
  hold_reason: string | null;
  held_by: string | null;
  held_at: string | null;
  transaction_id: string | null;
  checks: PolicyCheck[];
  approvals: Approval[];
  audit_log: AuditEntry[];
  /** False means the audit log was tampered with — show it loudly. */
  audit_chain_valid: boolean;
}

/** Frozen at payment. Nothing here can change again. */
export interface TransactionRecord {
  id: string;
  requisition_id: string;
  requisition_ref: string;
  vendor_name: string;
  vendor_account: string;
  amount: number;
  currency: string;
  category: string;
  project_code: string;
  grant_code: string | null;
  bank_reference: string;
  paid_by: string;
  paid_at: string;
  payees: Payee[];
  exceptions_count: number;
  locked: boolean;
  checks: PolicyCheck[];
  approvals: Approval[];
  audit_log: AuditEntry[];
}

export interface TransactionSummaryRow {
  id: string;
  requisition_ref: string;
  vendor_name: string;
  amount: number;
  currency: string;
  category: string;
  project_code: string;
  grant_code: string | null;
  paid_at: string;
  exceptions_count: number;
}

/** One released FAIL, as the auditor sees it. */
export interface AuditException {
  transaction_id: string;
  requisition_ref: string;
  check: string;
  policy_value: string | null;
  actual_value: string | null;
  reason: string | null;
  authority: string | null;
  approved_by: string | null;
}

export interface AuditSummary {
  org_id: string;
  generated_at: string;
  requisitions_total: number;
  requisitions_by_status: Record<string, number>;
  transactions_total: number;
  value_paid: number;
  exceptions_total: number;
  exceptions_unexplained: number;
  exceptions: AuditException[];
  /** False if any exception lacks a written reason. */
  audit_ready: boolean;
}
