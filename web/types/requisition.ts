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

export interface RequisitionWorkflow {
  org_id: string;
  steps: WorkflowStep[];
  currency: string;
  max_amount: number | null;
  allowed_categories: string[];
  forbidden_vendors: string[];
  approved_vendors: string[];
  required_documents: string[];
  duplicate_window_days: number;
  updated_at: string | null;
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
