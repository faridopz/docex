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
import { apiFetch, BASE, getToken } from "@/lib/session";
import type {
  AuditSummary,
  BudgetLine,
  ComplianceSummary,
  Decision,
  Payee,
  PaymentType,
  PolicyCheck,
  Requisition,
  RequisitionSummary,
  RequisitionWorkflow,
  ReqStatus,
  RulebookSummary,
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
  /** Payee bank/contact detail for the single-vendor path — matches what a
   * batch's Payee rows already carry per-payee. */
  vendor_bank_name?: string;
  vendor_tin?: string;
  vendor_phone_or_email?: string;
  /** "full", "advance", or "balance" — defaults to "full" server-side. */
  payment_type?: PaymentType;
  /** The expense breakdown, if any. `line_total` is ignored even if sent —
   * the server always recomputes it. */
  budget_lines?: BudgetLine[];
  description?: string;
  /** Field-receipt IDs backing this request. */
  receipt_ids?: string[];
  /** Document labels attached, e.g. "invoice", "purchase_order". */
  documents?: string[];
  /** A batch of payees (a stipend list, a beneficiary payout run) instead of
   * one vendor. When present, `amount` is ignored — the server always
   * recomputes it as the sum of these rows, so the two can never disagree. */
  payees?: Payee[];
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
      vendor_bank_name: body.vendor_bank_name ?? "",
      vendor_tin: body.vendor_tin ?? "",
      vendor_phone_or_email: body.vendor_phone_or_email ?? "",
      payment_type: body.payment_type ?? "full",
      budget_lines: JSON.stringify(body.budget_lines ?? []),
      description: body.description ?? "",
      receipt_ids: (body.receipt_ids ?? []).join(","),
      documents: (body.documents ?? []).join(","),
      payees: JSON.stringify(body.payees ?? []),
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

/** Pause a requisition at its current step. `reason` is required by the
 * server — this is not a decision, so it doesn't move off the step. */
export async function placeRequisitionOnHold(id: string, reason: string): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/hold`, {
    method: "POST",
    body: form({ reason }),
  });
}

export async function releaseRequisitionHold(id: string, notes = ""): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/release-hold`, {
    method: "POST",
    body: form({ notes }),
  });
}

/** Add a message to the requisition's discussion thread. Available at any
 * status, to anyone who can see the requisition — not role-gated. */
export async function addRequisitionComment(id: string, text: string): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/comments`, {
    method: "POST",
    body: form({ text }),
  });
}

// ─── attachments ────────────────────────────────────────────────────────────

/** Upload a real file — the invoice itself, not just a ticked document
 * label. Requires the org's requisition_attachments flag. */
export async function uploadRequisitionAttachment(id: string, file: File): Promise<Requisition> {
  const fd = new FormData();
  fd.append("file", file);
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/attachments`, {
    method: "POST",
    body: fd,
  });
}

/** Fetch an attached file's bytes, with the object's own filename/type. The
 * endpoint may redirect to a short-lived signed URL (production) or stream
 * the bytes directly (local dev) — fetch() follows the redirect either way,
 * so the caller always just gets a Blob back. Not routed through apiFetch:
 * the response here is binary or a redirect target, never JSON. */
export async function downloadRequisitionAttachment(
  reqId: string, attachmentId: string,
): Promise<Blob> {
  const token = getToken();
  const res = await fetch(
    `${BASE}/requisitions/${encodeURIComponent(reqId)}/attachments/${encodeURIComponent(attachmentId)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
  );
  if (!res.ok) {
    throw new Error(`Could not download this file (${res.status}).`);
  }
  return res.blob();
}

// ─── compliance check ───────────────────────────────────────────────────────

/** Check this requisition's real attachments against a compliance rulebook.
 * Requires requisition_compliance_check enabled. `rulebookId`, when given,
 * checks against that specific rulebook for this one run instead of the
 * workflow's configured default (Settings → Workflow) — lets whoever is
 * running the check pick the policy that actually applies to this request,
 * rather than always using whatever was set up once, org-wide. Costs a
 * real Claude API call server-side — not something to trigger silently. */
export async function runComplianceCheck(
  id: string, rulebookId?: string,
): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/compliance-check`, {
    method: "POST",
    body: form({ rulebook_id: rulebookId ?? "" }),
  });
}

// ─── audit findings ─────────────────────────────────────────────────────────

export interface AuditFinding {
  code: string;
  title: string;
  severity: "high" | "medium" | "low";
  /** What was found, in plain words. */
  detail: string;
  /** Why an auditor cares — shown, not hidden behind a tooltip. */
  why: string;
  /** The exact records involved, so the finding can be checked by hand. */
  refs: string[];
  amount: number;
}

export interface AuditFindingsReport {
  org_id: string;
  generated_at: string;
  requisitions_examined: number;
  transactions_examined: number;
  clean: boolean;
  by_severity: { high: number; medium: number; low: number };
  findings: AuditFinding[];
}

/** Run the audit tests over the organisation's records. Deterministic — every
 * finding is arithmetic or pattern matching over stored records, so an
 * auditor can reproduce it by hand. Sends the browser's UTC offset because
 * the working-hours test only means anything in the org's own time. */
export async function getAuditFindings(): Promise<AuditFindingsReport> {
  const offset = new Date().getTimezoneOffset();
  return apiFetch(`/audit/findings?tz_offset_minutes=${offset}`);
}

// ─── payee import ───────────────────────────────────────────────────────────

export interface ImportedPayeeRow {
  row_number: number;
  name: string;
  account_number: string;
  bank_name: string;
  amount: number;
  purpose: string;
  tin: string;
  phone_or_email: string;
  payee_type: Payee["payee_type"];
  ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface PayeeImportPreview {
  filename: string;
  detected_columns: Record<string, string>;
  headers_found: string[];
  total_rows: number;
  valid_count: number;
  problem_count: number;
  total_amount: number;
  max_payees: number;
  over_cap: boolean;
  rows: ImportedPayeeRow[];
}

/** Read a payee schedule out of a spreadsheet. CREATES NOTHING — it parses
 * and validates so the rows can be reviewed before anything is raised. The
 * confirmed rows then go through createRequisition() exactly as typed ones
 * do, which is what keeps an imported batch on the same policy checks,
 * approval chain and compliance check as every other requisition. */
export async function previewPayeeImport(file: File): Promise<PayeeImportPreview> {
  const fd = new FormData();
  fd.append("file", file);
  return apiFetch("/requisitions/payees/preview", { method: "POST", body: fd });
}

/** Send a requisition up or down the chain — escalate it to a later stage,
 * or hand it back to an earlier one without bouncing it to the submitter and
 * losing the reviews already done. The reason is required and read at audit.
 * Only the department currently holding it can do this. */
export async function routeRequisition(
  id: string, input: { target_step: string; reason: string },
): Promise<Requisition> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/route`, {
    method: "POST",
    body: form({ target_step: input.target_step, reason: input.reason }),
  });
}

// ─── emailed sign-off ───────────────────────────────────────────────────────

export interface SignoffRequestResult {
  /** True only if SMTP is configured AND the send succeeded. */
  sent: boolean;
  webhook: boolean;
  /** Always returned, so it can be copied and sent by hand when `sent` is
   * false. A demo where the link is unreachable teaches people the feature
   * doesn't work. */
  link: string;
  step: string;
  approver_email: string;
}

/** Email someone a unique, expiring link to sign off this requisition —
 * for an approver who is travelling, or anyone without a DOCex account.
 * Minting the link is an authenticated, audited act: it is recorded on the
 * requisition as a delegation before any email is attempted. */
export async function requestRequisitionSignoff(
  id: string,
  input: { step: string; approver_email: string; note?: string },
): Promise<SignoffRequestResult> {
  return apiFetch(`/requisitions/${encodeURIComponent(id)}/request-signoff`, {
    method: "POST",
    body: JSON.stringify({
      step: input.step,
      approver_email: input.approver_email,
      note: input.note ?? "",
    }),
  });
}

/** What an emailed approver sees before deciding. Deliberately enough to
 * decide on — amount, payee, purpose, every policy check — not just a ref. */
export interface SignoffView {
  requisition_ref: string;
  payee: string;
  amount: number;
  currency: string;
  amount_in_words: string;
  category: string;
  description: string;
  payment_type: string;
  submitted_by: string;
  submitted_at: string;
  step: string;
  step_label: string;
  approver_email: string;
  status: ReqStatus;
  checks: PolicyCheck[];
  blocking_count: number;
  attachment_count: number;
  compliance: ComplianceSummary | null;
  /** False when this link can no longer be acted on. */
  actionable: boolean;
  already_moved: boolean;
}

/** PUBLIC — no session. The token in the URL is the credential. */
export async function verifyRequisitionSignoff(token: string): Promise<SignoffView> {
  const res = await fetch(
    `${BASE}/requisitions/approve/verify/${encodeURIComponent(token)}`,
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `This approval link could not be opened (${res.status}).`);
  }
  return res.json();
}

/** PUBLIC — records the decision from the approver's link. */
export async function actOnRequisitionSignoff(
  token: string,
  input: { action: "approve" | "return" | "decline"; note?: string },
): Promise<{ recorded: boolean; requisition_ref: string; status: ReqStatus; current_step: string | null }> {
  const res = await fetch(`${BASE}/requisitions/approve/${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: input.action, note: input.note ?? "" }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Could not record that decision (${res.status}).`);
  }
  return res.json();
}

/** Saved compliance rulebooks, summary view — for the picker shown before
 * running a check. */
export async function listComplianceRulebooks(): Promise<RulebookSummary[]> {
  const r = await apiFetch<{ rulebooks: RulebookSummary[] }>("/compliance/rulebooks");
  return r.rulebooks;
}

// ─── export ─────────────────────────────────────────────────────────────────

/** Trigger a browser save for an already-fetched file. Object URL + a
 * throwaway anchor is the only way to control the saved filename from
 * script — a plain window.open() ignores it. */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ─── the organisation's own paperwork ─────────────────────────────────────

/** Which documents this signed-in person may download — the server answers
 * from the same rules the download routes enforce, so the screen never
 * offers a button that would be refused. */
export type DocumentPermissions = { voucher: boolean; payee_schedule: boolean };

export async function getDocumentPermissions(): Promise<DocumentPermissions> {
  return apiFetch<DocumentPermissions>("/requisitions/document-permissions");
}

/** A binary download whose filename the SERVER chooses — the voucher and the
 * payee schedule are named for the PV number, which only the server knows
 * once it has been issued. Refusals (403/409) carry a sentence meant for the
 * person, so that sentence is what gets thrown, not raw JSON. */
async function downloadNamed(path: string, fallbackName: string): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    let message = `Could not download this document (${res.status}).`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON — keep the generic message */
    }
    throw new Error(message);
  }
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  return { blob: await res.blob(), filename: match ? match[1] : fallbackName };
}

/** The organisation's own payment voucher (PDF), numbered on first export. */
export function downloadRequisitionVoucher(id: string, ref: string) {
  return downloadNamed(`/requisitions/${encodeURIComponent(id)}/voucher.pdf`, `voucher-${ref}.pdf`);
}

/** Every payee with FULL bank details (Excel). Finance/admin only, approved
 * payments only, and every download is written to the requisition's trail. */
export function downloadPayeeSchedule(id: string, ref: string) {
  return downloadNamed(`/requisitions/${encodeURIComponent(id)}/payees.xlsx`, `payees-${ref}.xlsx`);
}

/** Fetch a requisition's export packet as a Blob — the printable/pasteable
 * artifact, not the JSON detail view. Raw authenticated fetch(), like
 * downloadRequisitionAttachment: the response is binary, never JSON. */
export async function downloadRequisitionExport(
  id: string, format: "pdf" | "xlsx",
): Promise<Blob> {
  const token = getToken();
  const res = await fetch(
    `${BASE}/requisitions/${encodeURIComponent(id)}/export.${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Could not export this requisition (${res.status}).`);
  }
  return res.blob();
}

/** Fetch the weekly/monthly requisition log for a date range (YYYY-MM-DD,
 * inclusive both ends, in the caller's OWN local calendar — "today" means
 * their today, not UTC's) as a Blob — the audit sweep export.
 *
 * Sends the browser's own UTC offset (Date.getTimezoneOffset()) so the
 * server can shift the day boundary to match. Without this, anything raised
 * in the gap between local midnight and UTC midnight silently falls out of
 * "today" for any org east of UTC (NEEM/TA Connect, WAT, are exactly this
 * case for the first hour of every day). */
export async function downloadRequisitionLog(start: string, end: string): Promise<Blob> {
  const token = getToken();
  const q = new URLSearchParams({
    start, end, tz_offset_minutes: String(new Date().getTimezoneOffset()),
  });
  const res = await fetch(`${BASE}/requisitions/export/log.xlsx?${q.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Could not export the log (${res.status}).`);
  }
  return res.blob();
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
