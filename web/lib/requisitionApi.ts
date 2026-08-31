/**
 * Requisition API client — raise, review, decide, pay, audit.
 *
 * Thin typed wrappers over apiFetch (auth + friendly errors live there).
 * The backend takes multipart form fields for every write, so those calls
 * build FormData; apiFetch leaves its Content-Type alone.
 *
 * Idempotency: create and pay both accept a client-generated key. A retry
 * after a dropped connection replays the key and the server returns the
 * original record instead of raising a second requisition or paying twice.
 * This is the one guarantee a finance system cannot do without.
 */
import { apiFetch } from "@/lib/session";
import type {
  AuditSummary,
  Decision,
  Requisition,
  RequisitionSummary,
  RequisitionWorkflow,
  ReqStatus,
  TransactionRecord,
  TransactionSummaryRow,
} from "@/types/requisition";

/** A random key for one logical write. Stable across retries of that write. */
export function newIdempotencyKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `k-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

function form(fields: Record<string, string | number | undefined | null>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue;
    fd.append(k, String(v));
  }
  return fd;
}

// ─── raise ──────────────────────────────────────────────────────────────────

export interface NewRequisition {
  vendor_name: string;
  amount: number;
  category?: string;
  project_code?: string;
  grant_code?: string;
  vendor_account?: string;
  description?: string;
  /** Field-receipt IDs backing this request. */
  receipt_ids?: string[];
  /** Document labels attached, e.g. "invoice", "purchase_order". */
  documents?: string[];
  currency?: string;
}

export async function createRequisition(
  body: NewRequisition,
  idempotencyKey?: string,
): Promise<Requisition> {
  return apiFetch("/requisitions", {
    method: "POST",
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    body: form({
      vendor_name: body.vendor_name,
      amount: body.amount,
      category: body.category ?? "",
      project_code: body.project_code ?? "",
      grant_code: body.grant_code ?? "",
      vendor_account: body.vendor_account ?? "",
      description: body.description ?? "",
      receipt_ids: (body.receipt_ids ?? []).join(","),
      documents: (body.documents ?? []).join(","),
      currency: body.currency ?? "NGN",
    }),
  });
}

// ─── list ───────────────────────────────────────────────────────────────────

export async function listRequisitions(
  params: {
    status?: ReqStatus;
    step?: string;
    department?: string;
    grant_code?: string;
  } = {},
): Promise<RequisitionSummary[]> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.step) q.set("step", params.step);
  if (params.department) q.set("department", params.department);
  if (params.grant_code) q.set("grant_code", params.grant_code);
  const qs = q.toString();
  const r = await apiFetch<{ total: number; requisitions: RequisitionSummary[] }>(
    `/requisitions${qs ? `?${qs}` : ""}`,
  );
  return r.requisitions;
}

/** Everything currently waiting on the signed-in user's department. */
export async function listPendingForMe(): Promise<{
  department: string;
  steps: string[];
  total: number;
  requisitions: RequisitionSummary[];
}> {
  return apiFetch("/requisitions/pending");
}

// ─── workflow config ────────────────────────────────────────────────────────

export async function getWorkflow(): Promise<RequisitionWorkflow> {
  return apiFetch("/requisitions/workflow");
}

export async function setWorkflow(wf: RequisitionWorkflow): Promise<RequisitionWorkflow> {
  return apiFetch("/requisitions/workflow", {
    method: "PUT",
    body: JSON.stringify(wf),
  });
}

// ─── detail ─────────────────────────────────────────────────────────────────

export async function getRequisition(id: string): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}`);
}

// ─── decide ─────────────────────────────────────────────────────────────────

export interface DecideInput {
  decision: Decision;
  notes?: string;
  /** Policy check codes to release. Requires a reason and the authority. */
  overrides?: string[];
  override_reason?: string;
  override_authority?: string;
}

export async function decideRequisition(id: string, input: DecideInput): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/decide`, {
    method: "POST",
    body: form({
      decision: input.decision,
      notes: input.notes ?? "",
      overrides: (input.overrides ?? []).join(","),
      override_reason: input.override_reason ?? "",
      override_authority: input.override_authority ?? "",
    }),
  });
}

export async function resubmitRequisition(id: string, notes = ""): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/resubmit`, {
    method: "POST",
    body: form({ notes }),
  });
}

// ─── payment ────────────────────────────────────────────────────────────────

export async function payRequisition(
  id: string,
  bankReference: string,
  idempotencyKey?: string,
): Promise<TransactionRecord> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/pay`, {
    method: "POST",
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    body: form({ bank_reference: bankReference }),
  });
}

export async function listPayments(
  params: { grant_code?: string; project_code?: string } = {},
): Promise<{ total: number; value: number; transactions: TransactionSummaryRow[] }> {
  const q = new URLSearchParams();
  if (params.grant_code) q.set("grant_code", params.grant_code);
  if (params.project_code) q.set("project_code", params.project_code);
  const qs = q.toString();
  return apiFetch(`/payments${qs ? `?${qs}` : ""}`);
}

export async function getPayment(txnId: string): Promise<TransactionRecord> {
  return apiFetch(`/payments/${encodeURIComponent(txnId)}`);
}

// ─── audit ──────────────────────────────────────────────────────────────────

export async function getAuditSummary(): Promise<AuditSummary> {
  return apiFetch("/audit/summary");
}
