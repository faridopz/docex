/**
 * ERP workflow API client — transactions, notifications, vouchers, per-diem,
 * dashboard. Thin typed wrappers over apiFetch (which handles auth + errors).
 */
import { apiFetch } from "@/lib/session";
import type {
  AppNotification,
  AuthUser,
  DashboardSummary,
  Department,
  Transaction,
  TransactionSummary,
  TxnState,
  Voucher,
} from "@/types/erp";

// ─── auth ───────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
  return apiFetch("/auth/login", {
    method: "POST",
    auth: false,
    body: JSON.stringify({ email, password }),
  });
}

export async function registerUser(
  body: { email: string; name: string; password: string; department: Department; role?: string },
  adminToken?: string,
): Promise<AuthUser> {
  return apiFetch("/auth/register", {
    method: "POST",
    auth: false,
    headers: adminToken ? { Authorization: `Bearer ${adminToken}` } : undefined,
    body: JSON.stringify(body),
  });
}

export async function listUsers(): Promise<AuthUser[]> {
  const r = await apiFetch<{ users: AuthUser[] }>("/auth/users");
  return r.users;
}

// ─── departments (org-defined) ──────────────────────────────────────────────

export interface DepartmentDef {
  key: string;
  name: string;
  description: string;
  order: number;
  is_final_authority: boolean;
}

export async function listDepartments(): Promise<{
  departments: DepartmentDef[];
  state_owners: Record<string, string>;
}> {
  return apiFetch("/departments");
}

export async function createDepartment(body: {
  name: string;
  description?: string;
  order?: number;
  is_final_authority?: boolean;
}): Promise<DepartmentDef> {
  return apiFetch("/departments", { method: "POST", body: JSON.stringify(body) });
}

export async function updateDepartment(
  key: string,
  body: { name?: string; description?: string; order?: number; is_final_authority?: boolean },
): Promise<DepartmentDef> {
  return apiFetch(`/departments/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function deleteDepartment(key: string): Promise<void> {
  await apiFetch(`/departments/${encodeURIComponent(key)}`, { method: "DELETE" });
}

export async function setStateOwner(
  state: string,
  department: string | null,
): Promise<{ state_owners: Record<string, string> }> {
  return apiFetch(`/departments/routing/${encodeURIComponent(state)}`, {
    method: "PUT",
    body: JSON.stringify({ department }),
  });
}

// ─── dashboard ──────────────────────────────────────────────────────────────

export async function getDashboard(department?: Department): Promise<DashboardSummary> {
  const q = department ? `?department=${department}` : "";
  return apiFetch(`/dashboard${q}`);
}

// ─── transactions ─────────────────────────────────────────────────────────────

export async function listTransactions(params: { department?: Department; state?: TxnState } = {}): Promise<TransactionSummary[]> {
  const q = new URLSearchParams();
  if (params.department) q.set("department", params.department);
  if (params.state) q.set("state", params.state);
  const qs = q.toString();
  const r = await apiFetch<{ transactions: TransactionSummary[] }>(`/transactions${qs ? `?${qs}` : ""}`);
  return r.transactions;
}

export async function getTransaction(ref: string): Promise<Transaction> {
  return apiFetch(`/transactions/${encodeURIComponent(ref)}`);
}

export async function getAllowedTransitions(ref: string): Promise<{ state: TxnState; allowed: TxnState[] }> {
  return apiFetch(`/transactions/${encodeURIComponent(ref)}/next`);
}

export async function transitionTransaction(
  ref: string,
  body: { to_state: TxnState; department?: Department; actor?: string; note?: string },
): Promise<Transaction> {
  return apiFetch(`/transactions/${encodeURIComponent(ref)}/transition`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function viewTransaction(ref: string, department?: Department, actor?: string): Promise<Transaction> {
  return apiFetch(`/transactions/${encodeURIComponent(ref)}/view`, {
    method: "POST",
    body: JSON.stringify({ department, actor }),
  });
}

export async function addTransactionNote(
  ref: string,
  note: string,
  department?: Department,
  actor?: string,
): Promise<Transaction> {
  return apiFetch(`/transactions/${encodeURIComponent(ref)}/note`, {
    method: "POST",
    body: JSON.stringify({ note, department, actor }),
  });
}

// ─── notifications ────────────────────────────────────────────────────────────

export async function listNotifications(
  department: Department,
  unreadOnly = false,
): Promise<{ department: Department; unread: number; notifications: AppNotification[] }> {
  return apiFetch(`/notifications?department=${department}&unread_only=${unreadOnly}`);
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  return apiFetch(`/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead(department: Department): Promise<{ marked_read: number }> {
  return apiFetch(`/notifications/read-all?department=${department}`, { method: "POST" });
}

// ─── vouchers / per-diem ────────────────────────────────────────────────────

export interface ParticipantInput {
  participant_name: string;
  role?: string;
  rate_card_id?: string;
  rate_per_day?: number;
  num_days?: number;
  default_covered?: string[];
  receipts?: { filename?: string; amount?: number | null; category?: string }[];
}

export async function buildVoucher(body: {
  event_name: string;
  currency?: string;
  created_by?: string;
  participants: ParticipantInput[];
}): Promise<Voucher> {
  return apiFetch(`/vouchers`, { method: "POST", body: JSON.stringify(body) });
}

export async function submitVoucher(id: string): Promise<Voucher> {
  return apiFetch(`/vouchers/${id}/submit`, { method: "POST" });
}

export async function listVouchers(): Promise<Voucher[]> {
  const r = await apiFetch<{ vouchers: Voucher[] }>(`/vouchers`);
  return r.vouchers;
}

// ─── rate cards (per-diem policy source) ────────────────────────────────────

export interface RateCardLite {
  id: string;
  name: string;
  default_rate_per_day: number;
  currency: string;
  meals_weight?: number;
  lodging_weight?: number;
  incidentals_weight?: number;
  roles?: { role: string; amount_per_day: number }[];
}

export async function listRateCards(): Promise<RateCardLite[]> {
  const r = await apiFetch<{ rate_cards: RateCardLite[] }>(`/rate-cards`);
  return r.rate_cards;
}
