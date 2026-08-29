/**
 * ERP workflow types — mirror the FastAPI models (models.py) for the
 * cross-department workflow: transactions, notifications, vouchers, auth.
 * Kept in a dedicated file so the large types/index.ts stays focused.
 */

// A department KEY. Organisations define their own departments (see the
// departments registry / admin screen), so this is a plain string rather than a
// fixed union — EVA's Program/Compliance/Finance/TLFA/ED differ from the
// defaults. Use deptLabel() in lib/erpFormat for display names.
export type Department = string;
export type Role = "viewer" | "reviewer" | "approver" | "admin";

export type TxnKind =
  | "compliance_check"
  | "payment_run"
  | "voucher"
  | "travel_claim";

export type TxnState =
  | "submitted"
  | "intake"
  | "compliance_review"
  | "finance_review"
  | "approval"
  | "paid"
  | "returned";

export type TxnEventType =
  | "created"
  | "state_changed"
  | "viewed"
  | "noted"
  | "returned"
  | "approved"
  | "paid"
  | "linked";

export interface TxnEvent {
  type: TxnEventType;
  timestamp: string;
  actor?: string | null;
  department?: Department | null;
  from_state?: TxnState | null;
  to_state?: TxnState | null;
  note?: string | null;
}

export interface Transaction {
  id: string;
  ref: string;
  kind: TxnKind;
  title: string;
  state: TxnState;
  owner_department?: Department | null;
  source_kind?: TxnKind | null;
  source_id?: string | null;
  amount?: number | null;
  currency: string;
  viewed_by: string[];
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  history: TxnEvent[];
}

export interface TransactionSummary {
  ref: string;
  kind: TxnKind;
  title: string;
  state: TxnState;
  owner_department?: Department | null;
  amount?: number | null;
  currency: string;
  updated_at?: string | null;
}

export type NotificationKind =
  | "assigned"
  | "returned"
  | "approved"
  | "paid"
  | "mention";

export interface AppNotification {
  id: string;
  txn_ref: string;
  to_department: Department;
  kind: NotificationKind;
  title: string;
  body: string;
  read: boolean;
  actor?: string | null;
  created_at?: string | null;
}

export interface DashboardSummary {
  department: Department;
  unread_notifications: number;
  pending_on_me: number;
  counts_by_state: Record<string, number>;
  total_value_pending: number;
  currency: string;
  recent: TransactionSummary[];
}

export interface VoucherLine {
  participant_name: string;
  role?: string | null;
  days: number;
  per_diem_entitlement: number;
  reimbursable_total: number;
  amount: number;
  flag_count: number;
  summary: string;
}

export interface Voucher {
  id: string;
  event_name: string;
  lines: VoucherLine[];
  total: number;
  currency: string;
  participant_count: number;
  flagged_count: number;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  txn_id?: string | null;
  txn_ref?: string | null;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  department: Department;
  role: Role;
  active?: boolean;
  created_at?: string | null;
}
