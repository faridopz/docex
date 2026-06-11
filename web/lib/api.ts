import type {
  ApplicantExtraction,
  ApplicantInput,
  AssistantBrief,
  AttendanceCollection,
  AttendanceCollectionSummary,
  CollectedAttendee,
  PublicCollectionInfo,
  BankVerifyBatchResult,
  BatchExtractionResponse,
  BatchVerifyListResponse,
  BatchVerifySummary,
  CheckListResponse,
  CheckSummary,
  ComplianceCheckBatchResult,
  ComplianceCheckResult,
  DiagnosticReport,
  DiagnosticReportSummary,
  KnowledgeAnswer,
  PolicyRule,
  PolicyRulebook,
  Question,
  RateCard,
  RateLine,
  RulebookListResponse,
  RulebookSummary,
  SingleExtractionResponse,
  SlideDeck,
  SlideDeckSummary,
} from "@/types";
import { assignBucket } from "@/lib/buckets";
import { throwFriendly } from "@/lib/errors";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// ─── Single applicant extraction ──────────────────────────────────────────────

export async function extractSingle(
  applicantName: string,
  files: File[],
  questions: Question[],
): Promise<SingleExtractionResponse> {
  const body = new FormData();
  body.append("applicant_name", applicantName);
  body.append("questions", JSON.stringify(questions));
  for (const f of files) body.append("documents", f);

  const res = await fetch(`${BASE}/extract/single`, { method: "POST", body });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<SingleExtractionResponse>;
}

// ─── Batch extraction ─────────────────────────────────────────────────────────

export async function extractBatch(
  applicants: ApplicantInput[],
  questions: Question[],
): Promise<BatchExtractionResponse> {
  const body = new FormData();
  body.append("questions", JSON.stringify(questions));

  // Map each applicant to their filenames (must match what we upload)
  const applicantMeta = applicants.map((ap) => ({
    id: ap.id,
    name: ap.name,
    filenames: ap.files.map((f) => f.name),
  }));
  body.append("applicants", JSON.stringify(applicantMeta));

  // Upload all files from all applicants together
  for (const ap of applicants) {
    for (const f of ap.files) body.append("documents", f);
  }

  const res = await fetch(`${BASE}/extract/batch`, { method: "POST", body });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<BatchExtractionResponse>;
}

// ─── Follow-up note drafting ──────────────────────────────────────────────────

export interface FollowupDraft {
  applicant_id: string;
  applicant_name: string;
  note: string;
}

export async function draftFollowups(
  applicants: ApplicantExtraction[],
  questions: Question[],
  templateId?: string | null,
): Promise<FollowupDraft[]> {
  const res = await fetch(`${BASE}/draft-followups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // template_id (snake_case) matches the Pydantic schema on the backend.
    // The drafter uses it to pick the right system prompt — for
    // quarterly-report-review it says "partner" not "applicant", and
    // asks for an addendum instead of a resubmission.
    body: JSON.stringify({
      applicants,
      questions,
      template_id: templateId ?? null,
    }),
  });
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as { drafts: FollowupDraft[] };
  return data.drafts;
}

export function exportFollowupsAsText(
  drafts: { applicant_name: string; note: string }[],
  filename = "docex-followup-notes.txt",
): void {
  const text = drafts
    .map((d) => `=== ${d.applicant_name} ===\n\n${d.note}`)
    .join("\n\n\n");
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Excel export ─────────────────────────────────────────────────────────────
// Uses SheetJS (xlsx). Import is dynamic to avoid SSR issues.

export async function exportToExcel(
  applicants: BatchExtractionResponse["applicants"],
  questions: Question[],
  filename?: string,
  templateId?: string,
): Promise<void> {
  const resolvedFilename =
    filename ??
    (templateId ? `docex-${templateId}-results.xlsx` : "docex-results.xlsx");
  const XLSX = await import("xlsx");

  // Build rows: header + one row per applicant.
  // Bucket + justification go in their own columns up front so an auditor
  // reading the Excel sees the summary classification before the detail.
  const header = [
    "Applicant",
    "Bucket",
    "Bucket justification",
    "Documents read",
    ...questions.flatMap((q) => [
      q.text,                        // answer column
      `${q.text} — Source`,          // source doc column
      `${q.text} — Confidence`,      // confidence column
      `${q.text} — Notes`,           // search notes column
    ]),
    "Errors",
  ];

  const rows = applicants.map((ap) => {
    const answerMap = new Map(ap.answers.map((a) => [a.question_id, a]));
    const assignment = assignBucket(ap.answers);

    const cells = questions.flatMap((q) => {
      const a = answerMap.get(q.id);
      if (!a) return ["", "", "not_found", ""];
      const source = a.source_document
        ? a.source_page != null
          ? `${a.source_document} · p.${a.source_page}`
          : a.source_document
        : "";
      return [
        a.answer ?? "",
        source,
        a.confidence,
        a.search_notes ?? "",
      ];
    });

    return [
      ap.applicant_name,
      assignment.bucket.label,
      assignment.justification,
      ap.documents.join(", "),
      ...cells,
      ap.error ?? "",
    ];
  });

  const ws = XLSX.utils.aoa_to_sheet([header, ...rows]);

  // Style: freeze the header row and applicant column
  ws["!freeze"] = { xSplit: 1, ySplit: 1 };

  // Auto-width columns (rough estimate)
  const colWidths = header.map((h, i) => {
    const maxLen = Math.max(
      h.length,
      ...rows.map((r) => String(r[i] ?? "").length),
    );
    return { wch: Math.min(maxLen + 2, 60) };
  });
  ws["!cols"] = colWidths;

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Results");
  XLSX.writeFile(wb, resolvedFilename);
}

// ─── JSON export ──────────────────────────────────────────────────────────────

export function exportJson(data: unknown, filename = "docex-results.json"): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Compliance ────────────────────────────────────────────────────────────
//
// One function per endpoint in api/compliance_routes.py. Errors thrown with
// the response body so the UI can show what actually went wrong instead of
// a bare status code. Pattern matches the extraction client above.

export async function interpretPolicy(
  name: string,
  files: File[],
): Promise<PolicyRulebook> {
  const body = new FormData();
  body.append("name", name);
  for (const f of files) body.append("policy_documents", f);

  const res = await fetch(`${BASE}/compliance/policy`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to interpret policy (${res.status}): ${detail}`);
  }
  return res.json() as Promise<PolicyRulebook>;
}

export async function listRulebooks(): Promise<RulebookSummary[]> {
  const res = await fetch(`${BASE}/compliance/rulebooks`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to load rulebooks (${res.status}): ${detail}`);
  }
  const data = (await res.json()) as RulebookListResponse;
  return data.rulebooks;
}

export async function getRulebook(id: string): Promise<PolicyRulebook> {
  const res = await fetch(
    `${BASE}/compliance/rulebooks/${encodeURIComponent(id)}`,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to load rulebook (${res.status}): ${detail}`);
  }
  return res.json() as Promise<PolicyRulebook>;
}

export async function updateRulebook(
  id: string,
  body: {
    name?: string;
    rules: PolicyRule[];
    interpretation_notes?: string | null;
    notification_email?: string | null;
    notification_trigger?: string | null;
  },
): Promise<PolicyRulebook> {
  const res = await fetch(
    `${BASE}/compliance/rulebooks/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: body.name ?? null,
        rules: body.rules,
        interpretation_notes: body.interpretation_notes ?? null,
        notification_email: body.notification_email ?? null,
        notification_trigger: body.notification_trigger ?? null,
      }),
    },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to update rulebook (${res.status}): ${detail}`);
  }
  return res.json() as Promise<PolicyRulebook>;
}

export async function deleteRulebook(id: string): Promise<void> {
  const res = await fetch(
    `${BASE}/compliance/rulebooks/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to delete rulebook (${res.status}): ${detail}`);
  }
}

export interface RouteSuggestion {
  rulebook_id: string;
  rulebook_name: string;
  score: number;
  confidence: "high" | "medium" | "low";
  matched_terms: string[];
}

/** Auto-rank saved policy sets by fit to the uploaded payment documents. */
export async function routePayment(files: File[]): Promise<RouteSuggestion[]> {
  const body = new FormData();
  for (const f of files) body.append("payment_documents", f);
  const res = await fetch(`${BASE}/compliance/route`, {
    method: "POST",
    body,
  });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<RouteSuggestion[]>;
}

export async function checkPaymentSingle(
  rulebookId: string,
  paymentLabel: string,
  files: File[],
): Promise<ComplianceCheckResult> {
  const body = new FormData();
  body.append("rulebook_id", rulebookId);
  body.append("payment_label", paymentLabel);
  for (const f of files) body.append("payment_documents", f);

  const res = await fetch(`${BASE}/compliance/check/single`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Compliance check failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<ComplianceCheckResult>;
}

export interface PaymentInput {
  label: string;
  files: File[];
}

export async function checkPaymentBatch(
  rulebookId: string,
  payments: PaymentInput[],
): Promise<ComplianceCheckBatchResult> {
  const body = new FormData();
  body.append("rulebook_id", rulebookId);

  // Map each payment to its filenames so the backend can pluck them out
  // of the combined upload — same shape as /extract/batch.
  const meta = payments.map((p) => ({
    label: p.label,
    filenames: p.files.map((f) => f.name),
  }));
  body.append("payments", JSON.stringify(meta));

  for (const p of payments) {
    for (const f of p.files) body.append("documents", f);
  }

  const res = await fetch(`${BASE}/compliance/check/batch`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Batch compliance check failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<ComplianceCheckBatchResult>;
}

// ── Saved check CRUD + approval ────────────────────────────────────────────

export async function listChecks(): Promise<CheckSummary[]> {
  const res = await fetch(`${BASE}/compliance/checks`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to load checks (${res.status}): ${detail}`);
  }
  const data = (await res.json()) as CheckListResponse;
  return data.checks;
}

export async function getCheck(id: string): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(id)}`,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to load check (${res.status}): ${detail}`);
  }
  return res.json() as Promise<ComplianceCheckResult>;
}

export async function approveCheck(
  id: string,
  signature?: { signature_data_url?: string | null; signed_name?: string | null },
): Promise<ComplianceCheckResult> {
  const init: RequestInit = { method: "POST" };
  if (signature && (signature.signature_data_url || signature.signed_name)) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify({
      signature_data_url: signature.signature_data_url ?? null,
      signed_name: signature.signed_name ?? null,
    });
  }
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(id)}/approve`,
    init,
  );
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<ComplianceCheckResult>;
}

export async function unapproveCheck(id: string): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(id)}/unapprove`,
    { method: "POST" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to unapprove check (${res.status}): ${detail}`);
  }
  return res.json() as Promise<ComplianceCheckResult>;
}

export async function deleteCheck(id: string): Promise<void> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to delete check (${res.status}): ${detail}`);
  }
}

// ── Excel exports for compliance ──────────────────────────────────────────
// Generated client-side via SheetJS (xlsx). Each compliance check exports
// as a 2-sheet workbook (Summary + Findings) so finance teams can sort,
// filter, and append columns for their own notes. The bulk export gives
// one row per check — useful for monthly audit reports.

export async function exportCheckToExcel(
  check: ComplianceCheckResult,
  rulesForLookup: PolicyRule[],
  filename?: string,
): Promise<void> {
  const XLSX = await import("xlsx");

  // Sheet 1 — Summary (key/value pairs, scannable)
  const counts = {
    pass: 0,
    flag: 0,
    block: 0,
    not_applicable: 0,
    insufficient_evidence: 0,
  };
  for (const r of check.results) counts[r.verdict]++;

  const summaryRows: (string | number)[][] = [
    ["Payment label", check.payment_label],
    ["Payment ID", check.payment_id],
    ["Verdict", check.overall_verdict],
    ["Summary", check.overall_summary],
    ["Rulebook", check.rulebook_name],
    ["Check date", check.created_at ?? ""],
    ["Approved", check.approved ? "Yes" : "No"],
    ["Approved date", check.approved_at ?? ""],
    ["Documents", check.documents.join(", ")],
    ["Total rules evaluated", check.results.length],
    ["Pass", counts.pass],
    ["Flag", counts.flag],
    ["Block", counts.block],
    ["Need info", counts.insufficient_evidence],
    ["N/A", counts.not_applicable],
  ];
  const summarySheet = XLSX.utils.aoa_to_sheet(summaryRows);
  summarySheet["!cols"] = [{ wch: 22 }, { wch: 90 }];

  // Sheet 2 — Findings (one row per rule × applied-document)
  const findingsHeader = [
    "#",
    "Rule ID",
    "Clause",
    "Category",
    "Rule description",
    "Applied to",
    "Verdict",
    "Confidence",
    "Reasoning",
    "Policy citation",
    "Payment evidence",
    "Missing evidence",
  ];
  const findingsRows = check.results.map((r, i) => {
    const rule = rulesForLookup.find((rr) => rr.id === r.rule_id);
    return [
      i + 1,
      r.rule_id,
      rule?.clause_reference ?? "",
      rule?.category ?? "",
      r.rule_description,
      r.applied_to_document ?? "(payment-level)",
      r.verdict,
      r.confidence,
      r.reasoning,
      r.policy_citation ?? "",
      r.payment_evidence ?? "",
      (r.missing_evidence ?? []).join("; "),
    ];
  });
  const findingsSheet = XLSX.utils.aoa_to_sheet([findingsHeader, ...findingsRows]);
  // Auto-ish column widths (capped at 60 chars so the workbook stays readable)
  findingsSheet["!cols"] = findingsHeader.map((h, i) => {
    const maxLen = Math.max(
      h.length,
      ...findingsRows.map((r) => String(r[i] ?? "").length),
    );
    return { wch: Math.min(maxLen + 2, 60) };
  });
  // Freeze the header row + the first column (rule index)
  findingsSheet["!freeze"] = { xSplit: 1, ySplit: 1 };

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, summarySheet, "Summary");
  XLSX.utils.book_append_sheet(wb, findingsSheet, "Findings");

  const fn =
    filename ??
    `compliance-${(check.payment_label || check.payment_id).replace(/[^a-zA-Z0-9-_.]+/g, "_")}.xlsx`;
  XLSX.writeFile(wb, fn);
}

// Full auditor-style export of ONE check: the summary, the rule findings,
// AND the complete decision history (who did what, when — escalations,
// clarifications, notes, approvals, emails sent). This is the record an
// auditor asks for: the verdict plus the human trail behind it.
export async function exportCheckAuditHistory(
  check: ComplianceCheckResult,
  rulesForLookup: PolicyRule[],
  filename?: string,
): Promise<void> {
  const XLSX = await import("xlsx");

  const EVENT_LABEL: Record<string, string> = {
    check_run: "Check ran",
    note_added: "Note added",
    rule_dismissed: "Flag dismissed",
    rule_escalated: "Rule escalated",
    clarification_requested: "Clarification requested",
    clarification_received: "Clarification received",
    escalated: "Escalated",
    approved: "Approved",
    unapproved: "Approval revoked",
  };

  // Sheet 1 — Summary
  const counts = { pass: 0, flag: 0, block: 0, not_applicable: 0, insufficient_evidence: 0 };
  for (const r of check.results) counts[r.verdict]++;
  const summaryRows: (string | number)[][] = [
    ["Payment label", check.payment_label],
    ["Payment ID", check.payment_id],
    ["Verdict", check.overall_verdict],
    ["Summary", check.overall_summary],
    ["Rulebook (policy set)", check.rulebook_name],
    ["Check date", check.created_at ?? ""],
    ["Approved", check.approved ? "Yes" : "No"],
    ["Approved date", check.approved_at ?? ""],
    ["Documents", check.documents.join(", ")],
    ["Rules evaluated", check.results.length],
    ["Pass", counts.pass],
    ["Flag", counts.flag],
    ["Block", counts.block],
    ["Need info", counts.insufficient_evidence],
    ["N/A", counts.not_applicable],
  ];
  const summarySheet = XLSX.utils.aoa_to_sheet(summaryRows);
  summarySheet["!cols"] = [{ wch: 22 }, { wch: 90 }];

  // Sheet 2 — Rule findings
  const findingsHeader = [
    "#", "Rule ID", "Clause", "Category", "Rule", "Applied to",
    "Verdict", "Confidence", "Reasoning", "Policy citation", "Payment evidence",
  ];
  const findingsRows = check.results.map((r, i) => {
    const rule = rulesForLookup.find((rr) => rr.id === r.rule_id);
    return [
      i + 1, r.rule_id, rule?.clause_reference ?? "", rule?.category ?? "",
      r.rule_description, r.applied_to_document ?? "(payment-level)",
      r.verdict, r.confidence, r.reasoning,
      r.policy_citation ?? "", r.payment_evidence ?? "",
    ];
  });
  const findingsSheet = XLSX.utils.aoa_to_sheet([findingsHeader, ...findingsRows]);
  findingsSheet["!cols"] = findingsHeader.map((h, i) => ({
    wch: Math.min(
      Math.max(h.length, ...findingsRows.map((r) => String(r[i] ?? "").length)) + 2,
      60,
    ),
  }));
  findingsSheet["!freeze"] = { xSplit: 0, ySplit: 1 };

  // Sheet 3 — Audit history (the decision log, chronological)
  const historyHeader = [
    "#", "When", "Event", "By", "Detail", "Related rule", "Signed by", "Emailed to",
  ];
  const log = check.decision_log ?? [];
  const historyRows = log.map((e, i) => [
    i + 1,
    e.timestamp ?? "",
    EVENT_LABEL[e.type] ?? e.type,
    e.actor ?? "",
    e.note ?? "",
    e.rule_description ?? "",
    e.signed_name ?? "",
    e.notified_email ?? "",
  ]);
  const historySheet = XLSX.utils.aoa_to_sheet(
    historyRows.length ? [historyHeader, ...historyRows] : [historyHeader, ["—", "No recorded actions yet", "", "", "", "", "", ""]],
  );
  historySheet["!cols"] = [
    { wch: 4 }, { wch: 22 }, { wch: 22 }, { wch: 20 },
    { wch: 60 }, { wch: 40 }, { wch: 20 }, { wch: 28 },
  ];
  historySheet["!freeze"] = { xSplit: 0, ySplit: 1 };

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, summarySheet, "Summary");
  XLSX.utils.book_append_sheet(wb, findingsSheet, "Rule findings");
  XLSX.utils.book_append_sheet(wb, historySheet, "Audit history");

  const fn =
    filename ??
    `audit-${(check.payment_label || check.payment_id).replace(/[^a-zA-Z0-9-_.]+/g, "_")}.xlsx`;
  XLSX.writeFile(wb, fn);
}

export async function exportChecksListToExcel(
  checks: CheckSummary[],
  filename = "compliance-checks.xlsx",
): Promise<void> {
  const XLSX = await import("xlsx");

  const header = [
    "Payment label",
    "Verdict",
    "Approved",
    "Approved date",
    "Rulebook",
    "Check date",
    "Documents",
    "Summary",
    "Payment ID",
  ];
  const rows = checks.map((c) => [
    c.payment_label,
    c.overall_verdict,
    c.approved ? "Yes" : "No",
    c.approved_at ?? "",
    c.rulebook_name,
    c.created_at ?? "",
    c.document_count,
    c.overall_summary,
    c.payment_id,
  ]);

  const sheet = XLSX.utils.aoa_to_sheet([header, ...rows]);
  sheet["!cols"] = header.map((h, i) => {
    const maxLen = Math.max(
      h.length,
      ...rows.map((r) => String(r[i] ?? "").length),
    );
    return { wch: Math.min(maxLen + 2, 80) };
  });
  sheet["!freeze"] = { xSplit: 0, ySplit: 1 };

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, sheet, "Compliance Checks");
  XLSX.writeFile(wb, filename);
}

// ─── Bank Verify ─────────────────────────────────────────────────────────────
//
// Bank Verify is DOCex's third primitive. The API surface mirrors the
// compliance pattern — multipart upload for the heavy operation, JSON
// reads + deletes for everything else. exportBatchToXlsx triggers a file
// download directly because the backend already produces a polished xlsx
// (colour-coded by verdict) — no need to re-emit it on the client.

/**
 * Run a verification batch against a payment schedule.
 *
 * @param schedule  The .xlsx file containing recipient + account + bank columns.
 * @param purpose   WHY the verification ran (event_payment, grantee_disbursement,
 *                  vendor_payment, partner_reimbursement, or 'other' / custom).
 *                  Tags the audit trail and routes future notifications.
 * @param purposeDetail Optional free-text elaboration. Especially useful when
 *                  purpose is 'other' — describes the specific use-case.
 * @param delayMs   Delay between Paystack calls. 200ms keeps us under test-
 *                  mode's ~60 RPM limit. Drop to 50 in live mode.
 */
export async function verifyBankBatch(
  schedule: File,
  purpose: string,
  purposeDetail?: string,
  delayMs = 200,
): Promise<BankVerifyBatchResult> {
  const body = new FormData();
  body.append("schedule", schedule);
  body.append("purpose", purpose);
  if (purposeDetail) body.append("purpose_detail", purposeDetail);
  body.append("delay_ms", String(delayMs));
  body.append("persist", "true");

  const res = await fetch(`${BASE}/verify/bank-batch`, {
    method: "POST",
    body,
  });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<BankVerifyBatchResult>;
}

/** List every saved verification batch, newest first. */
export async function listVerifyBatches(): Promise<BatchVerifySummary[]> {
  const res = await fetch(`${BASE}/verify/batches`);
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as BatchVerifyListResponse;
  return data.batches;
}

/** Fetch one saved verification batch in full. */
export async function getVerifyBatch(
  batchId: string,
): Promise<BankVerifyBatchResult> {
  const res = await fetch(`${BASE}/verify/batches/${batchId}`);
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<BankVerifyBatchResult>;
}

/**
 * Trigger a browser download of the verified schedule .xlsx.
 *
 * The backend already produces a polished, colour-coded xlsx with summary
 * row + verdict columns appended — finance-officer-grade. We don't re-emit
 * on the client because the backend version benefits from the canonical
 * verdict colour palette already applied, and downloading direct from the
 * API avoids round-tripping the data through JS.
 */
export async function exportVerifyBatchToXlsx(batchId: string): Promise<void> {
  const res = await fetch(`${BASE}/verify/batches/${batchId}/export.xlsx`);
  if (!res.ok) await throwFriendly(res);
  const blob = await res.blob();
  // Pull the filename from Content-Disposition so the downloaded file
  // matches what the server set (with _verified suffix).
  const cd = res.headers.get("content-disposition") ?? "";
  const match = cd.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `bank-verify-${batchId}.xlsx`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Delete one saved verification batch. */
export async function deleteVerifyBatch(batchId: string): Promise<void> {
  const res = await fetch(`${BASE}/verify/batches/${batchId}`, {
    method: "DELETE",
  });
  if (!res.ok) await throwFriendly(res);
}

// ─── Attendance Payment Co-Pilot ───────────────────────────────────────────────
//
// First composite agent — chains attendance + payment-info parsing,
// fuzzy name matching, and (optionally) the Bank Verify primitive into
// a single button-click. Backend endpoints under /agents/attendance-payment.

/**
 * Run the agent: parse both files, cross-match, build a draft schedule.
 */
export async function runAttendanceAgent(
  attendance: File,
  paymentInfo: File,
  eventName: string,
  ratePerDay: number,
): Promise<import("@/types").AttendancePaymentRun> {
  const body = new FormData();
  body.append("attendance", attendance);
  body.append("payment_info", paymentInfo);
  body.append("event_name", eventName);
  body.append("rate_per_day", String(ratePerDay));
  body.append("persist", "true");

  const res = await fetch(`${BASE}/agents/attendance-payment/run`, {
    method: "POST",
    body,
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

/** List every saved attendance payment run, newest first. */
export async function listAttendanceRuns(): Promise<
  import("@/types").AttendancePaymentRunSummary[]
> {
  const res = await fetch(`${BASE}/agents/attendance-payment/runs`);
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as {
    runs: import("@/types").AttendancePaymentRunSummary[];
  };
  return data.runs;
}

/** Fetch one saved attendance payment run in full. */
export async function getAttendanceRun(
  runId: string,
): Promise<import("@/types").AttendancePaymentRun> {
  const res = await fetch(`${BASE}/agents/attendance-payment/runs/${runId}`);
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

/**
 * Hand the run's paid bucket to Bank Verify. Returns the resulting batch.
 * The run is updated server-side with the bank_verify_batch_id back-link.
 */
export async function verifyAttendanceRun(
  runId: string,
): Promise<import("@/types").BankVerifyBatchResult> {
  const res = await fetch(
    `${BASE}/agents/attendance-payment/runs/${runId}/verify`,
    { method: "POST" },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

/** Download the run's paid bucket as a payment schedule .xlsx. */
export async function exportAttendanceSchedule(runId: string): Promise<void> {
  const res = await fetch(
    `${BASE}/agents/attendance-payment/runs/${runId}/schedule.xlsx`,
  );
  if (!res.ok) await throwFriendly(res);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const match = cd.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `attendance-payment-${runId}.xlsx`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Delete a saved attendance run. */
export async function deleteAttendanceRun(runId: string): Promise<void> {
  const res = await fetch(`${BASE}/agents/attendance-payment/runs/${runId}`, {
    method: "DELETE",
  });
  if (!res.ok) await throwFriendly(res);
}

// ─── Rate cards ─────────────────────────────────────────────────────────────
//
// Reusable per-diem schedules. CRUD against /rate-cards. The Attendance
// Payment Agent run endpoint accepts a rate_card_id to apply per-role rates.

export async function listRateCards(): Promise<RateCard[]> {
  const res = await fetch(`${BASE}/rate-cards`);
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as { rate_cards: RateCard[] };
  return data.rate_cards;
}

export async function getRateCard(id: string): Promise<RateCard> {
  const res = await fetch(`${BASE}/rate-cards/${id}`);
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function createRateCard(payload: {
  name: string;
  default_rate_per_day: number;
  roles: RateLine[];
  currency?: string;
}): Promise<RateCard> {
  const res = await fetch(`${BASE}/rate-cards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ currency: "NGN", ...payload }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function updateRateCard(
  id: string,
  payload: {
    name: string;
    default_rate_per_day: number;
    roles: RateLine[];
    currency?: string;
  },
): Promise<RateCard> {
  const res = await fetch(`${BASE}/rate-cards/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ currency: "NGN", ...payload }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function deleteRateCard(id: string): Promise<void> {
  const res = await fetch(`${BASE}/rate-cards/${id}`, { method: "DELETE" });
  if (!res.ok) await throwFriendly(res);
}

// ─── Attendance agent — upgraded run signature ──────────────────────────────
//
// The original runAttendanceAgent above hard-codes file uploads + flat rate.
// runAttendanceAgentAdvanced lets the caller pass EITHER a file OR a Google
// Sheets URL per input, AND an optional rate_card_id. The original is kept
// for backward compat with any code that still calls it.

export async function runAttendanceAgentAdvanced(opts: {
  eventName: string;
  ratePerDay?: number;
  rateCardId?: string;
  attendanceFile?: File;
  attendanceSheetUrl?: string;
  paymentInfoFile?: File;
  paymentInfoSheetUrl?: string;
}): Promise<import("@/types").AttendancePaymentRun> {
  const body = new FormData();
  body.append("event_name", opts.eventName);
  if (opts.ratePerDay != null) body.append("rate_per_day", String(opts.ratePerDay));
  if (opts.rateCardId) body.append("rate_card_id", opts.rateCardId);
  if (opts.attendanceFile) body.append("attendance", opts.attendanceFile);
  if (opts.attendanceSheetUrl)
    body.append("attendance_sheet_url", opts.attendanceSheetUrl);
  if (opts.paymentInfoFile) body.append("payment_info", opts.paymentInfoFile);
  if (opts.paymentInfoSheetUrl)
    body.append("payment_info_sheet_url", opts.paymentInfoSheetUrl);
  body.append("persist", "true");

  const res = await fetch(`${BASE}/agents/attendance-payment/run`, {
    method: "POST",
    body,
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Self-Check Agent ──────────────────────────────────────────────────────
//
// Runtime diagnostic — exercises every primitive and reports health.
// V1 of the Self-Improvement Agent. Reports persist server-side.
//
// Admin-gated: when the backend has ADMIN_SECRET set, every /diagnostics/*
// request must include a matching X-Admin-Secret header. We read the
// secret from localStorage (set by the admin page's secret-input form).
// The custom AdminAuthError class lets the page surface a re-auth UI when
// the stored secret is missing or stale.

const ADMIN_SECRET_KEY = "docex.admin_secret";

export class AdminAuthError extends Error {
  constructor() {
    super("Admin authentication required");
    this.name = "AdminAuthError";
  }
}

function adminHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const secret = window.localStorage.getItem(ADMIN_SECRET_KEY);
  return secret ? { "X-Admin-Secret": secret } : {};
}

export function setAdminSecret(secret: string): void {
  if (typeof window === "undefined") return;
  if (secret) window.localStorage.setItem(ADMIN_SECRET_KEY, secret);
  else window.localStorage.removeItem(ADMIN_SECRET_KEY);
}

export function getAdminSecret(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ADMIN_SECRET_KEY);
}

export async function runDiagnostic(): Promise<DiagnosticReport> {
  const res = await fetch(`${BASE}/diagnostics/run`, {
    method: "POST",
    headers: adminHeaders(),
  });
  if (res.status === 404) throw new AdminAuthError();
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function getLastDiagnostic(): Promise<DiagnosticReport | null> {
  const res = await fetch(`${BASE}/diagnostics/last`, {
    headers: adminHeaders(),
  });
  // 404 has two meanings here: (a) admin gate rejected the request, or
  // (b) no reports exist yet. We disambiguate by attempting to read the
  // detail — but for simplicity we treat both as "no report available".
  // The page differentiates by calling runDiagnostic() (which throws
  // AdminAuthError on auth failure) when the user clicks "Run".
  if (res.status === 404) return null;
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function listDiagnosticReports(): Promise<DiagnosticReportSummary[]> {
  const res = await fetch(`${BASE}/diagnostics`, { headers: adminHeaders() });
  if (res.status === 404) throw new AdminAuthError();
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as { reports: DiagnosticReportSummary[] };
  return data.reports;
}

// ─── DOCex Assistant ────────────────────────────────────────────────────────
//
// Agentic narrator. Every result page calls this on mount with the result
// payload — Claude returns a plain-English briefing + ranked next actions.

export async function summarizeForAssistant(
  contextKind: string,
  payload: unknown,
  contextId?: string,
): Promise<AssistantBrief> {
  const res = await fetch(`${BASE}/assistant/summarize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      context_kind: contextKind,
      context_id: contextId ?? null,
      payload,
    }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Knowledge Hub ──────────────────────────────────────────────────────────
//
// Slide-deck ingestion + chat. Upload .pptx, save, ask questions, get cited
// answers. Same persistence + URL pattern as every other primitive.

export async function uploadDeck(
  file: File,
  opts?: { name?: string; description?: string; tags?: string[] },
): Promise<SlideDeck> {
  const body = new FormData();
  body.append("file", file);
  if (opts?.name) body.append("name", opts.name);
  if (opts?.description) body.append("description", opts.description);
  if (opts?.tags && opts.tags.length > 0)
    body.append("tags", opts.tags.join(", "));

  const res = await fetch(`${BASE}/knowledge/decks`, { method: "POST", body });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function listDecks(): Promise<SlideDeckSummary[]> {
  const res = await fetch(`${BASE}/knowledge/decks`);
  if (!res.ok) await throwFriendly(res);
  const data = (await res.json()) as { decks: SlideDeckSummary[] };
  return data.decks;
}

export async function getDeck(deckId: string): Promise<SlideDeck> {
  const res = await fetch(`${BASE}/knowledge/decks/${deckId}`);
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function deleteDeck(deckId: string): Promise<void> {
  const res = await fetch(`${BASE}/knowledge/decks/${deckId}`, {
    method: "DELETE",
  });
  if (!res.ok) await throwFriendly(res);
}

export async function chatWithDeck(
  deckId: string,
  question: string,
): Promise<KnowledgeAnswer> {
  const res = await fetch(`${BASE}/knowledge/decks/${deckId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Library-wide chat + folder management ──────────────────────────────────

export async function chatWithLibrary(
  question: string,
  opts?: { folder?: string | null; tags?: string[] },
): Promise<KnowledgeAnswer> {
  const res = await fetch(`${BASE}/knowledge/library/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      folder: opts?.folder ?? null,
      tags: opts?.tags ?? null,
    }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function updateDeck(
  deckId: string,
  patch: {
    name?: string;
    folder?: string | null;
    description?: string;
    tags?: string[];
  },
): Promise<SlideDeck> {
  const res = await fetch(`${BASE}/knowledge/decks/${deckId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...patch,
      // null folder must serialize to "" so the backend clears it
      folder: patch.folder === null ? "" : patch.folder,
    }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function suggestFolder(
  deckId: string,
): Promise<{ suggested_folder: string; reasoning: string }> {
  const res = await fetch(`${BASE}/knowledge/folders/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deck_id: deckId }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Compliance decision log ───────────────────────────────────────────────
//
// Officer notes + per-rule decisions. Both append to the check's
// decision_log (append-only on the backend) — every action is permanent
// and audit-defensible.

export async function addCheckNote(
  checkId: string,
  note: string,
  ruleId?: string,
): Promise<ComplianceCheckResult> {
  const res = await fetch(`${BASE}/compliance/checks/${checkId}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, rule_id: ruleId ?? null }),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function recordRuleDecision(
  checkId: string,
  ruleId: string,
  action: "dismiss" | "escalate" | "clarification_requested",
  reason: string,
): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${checkId}/rules/${ruleId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reason }),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Day 15: Approval-chain endpoints with optional signatures ───────────

export async function escalateCheck(
  checkId: string,
  payload: {
    pending_with: string;
    reason?: string;
    signature_data_url?: string | null;
    signed_name?: string | null;
  },
): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(checkId)}/escalate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function requestClarification(
  checkId: string,
  payload: {
    question: string;
    pending_with: string;
    rule_id?: string | null;
    signature_data_url?: string | null;
    signed_name?: string | null;
  },
): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(checkId)}/clarification`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function respondToClarification(
  checkId: string,
  payload: {
    response: string;
    signature_data_url?: string | null;
    signed_name?: string | null;
  },
): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(checkId)}/clarification/respond`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export async function listPendingChecks(): Promise<CheckSummary[]> {
  const res = await fetch(`${BASE}/compliance/pending`);
  if (!res.ok) await throwFriendly(res);
  const json = (await res.json()) as { checks: CheckSummary[] };
  return json.checks;
}

// ─── Verified approval sign-off (email magic-link) ──────────────────────────

/** Email a stage's approver a unique, verified sign-off link. */
export async function requestSignoff(
  checkId: string,
  stage: string,
  approverEmail: string,
): Promise<{ ok: boolean; emailed: boolean; link: string }> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(checkId)}/request-signoff`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage, approver_email: approverEmail }),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

export interface ApprovalTokenInfo {
  check_id: string;
  payment_label: string;
  rulebook_name: string;
  overall_verdict: "approved" | "flagged" | "blocked";
  overall_summary: string;
  stage: string;
  approver_email: string;
  workflow: string[];
  signed_stages: string[];
  already_signed: boolean;
  is_final_stage: boolean;
}

/** Public: validate an approval link → voucher summary for the approve page. */
export async function verifyApprovalToken(
  token: string,
): Promise<ApprovalTokenInfo> {
  const res = await fetch(
    `${BASE}/compliance/approve/verify/${encodeURIComponent(token)}`,
  );
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<ApprovalTokenInfo>;
}

/** Public: record a verified sign-off or return-for-changes. */
export async function submitApproval(
  token: string,
  action: "approve" | "return",
  note?: string,
): Promise<{ ok: boolean; approved?: boolean; returned?: boolean }> {
  const res = await fetch(
    `${BASE}/compliance/approve/${encodeURIComponent(token)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json();
}

// ─── Attendance Collections (native intake + self-check-in) ─────────────────

const COLL_BASE = `${BASE}/agents/attendance-payment/collections`;

export async function createCollection(input: {
  event_name: string;
  day_labels: string[];
  rate_per_day: number;
  rate_card_id?: string | null;
}): Promise<AttendanceCollection> {
  const res = await fetch(COLL_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<AttendanceCollection>;
}

export async function listCollections(): Promise<AttendanceCollectionSummary[]> {
  const res = await fetch(COLL_BASE);
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<AttendanceCollectionSummary[]>;
}

export async function getCollection(id: string): Promise<AttendanceCollection> {
  const res = await fetch(`${COLL_BASE}/${id}`);
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<AttendanceCollection>;
}

export async function updateCollection(
  id: string,
  patch: Partial<{
    event_name: string;
    day_labels: string[];
    rate_per_day: number;
    rate_card_id: string | null;
    attendees: CollectedAttendee[];
  }>,
): Promise<AttendanceCollection> {
  const res = await fetch(`${COLL_BASE}/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<AttendanceCollection>;
}

export async function deleteCollection(id: string): Promise<void> {
  const res = await fetch(`${COLL_BASE}/${id}`, { method: "DELETE" });
  if (!res.ok) await throwFriendly(res);
}

export async function buildCollectionRun(id: string): Promise<{ run_id: string }> {
  const res = await fetch(`${COLL_BASE}/${id}/run`, { method: "POST" });
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<{ run_id: string }>;
}

export async function getPublicCollection(
  token: string,
): Promise<PublicCollectionInfo> {
  const res = await fetch(`${COLL_BASE}/public/${token}`);
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<PublicCollectionInfo>;
}

export async function selfCheckIn(
  token: string,
  input: {
    name: string;
    organisation?: string;
    account_number?: string;
    bank_code?: string;
    bank_name?: string;
    role?: string;
    present_days?: string[];
  },
): Promise<void> {
  const res = await fetch(`${COLL_BASE}/public/${token}/attendees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) await throwFriendly(res);
}

// ─── External integrations (pluggable connectors) ───────────────────────────

export interface IntegrationInfo {
  id: string;
  label: string;
  configured: boolean;
  detail: string;
  synced: number;
}

export interface IntegrationSyncResult {
  provider: string;
  found: number;
  ingested: number;
  skipped: number;
  failed: number;
  errors: string[];
}

export async function listIntegrations(): Promise<IntegrationInfo[]> {
  const res = await fetch(`${BASE}/knowledge/integrations`);
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<IntegrationInfo[]>;
}

export async function syncIntegration(
  provider: string,
): Promise<IntegrationSyncResult> {
  const res = await fetch(
    `${BASE}/knowledge/integrations/${encodeURIComponent(provider)}/sync`,
    { method: "POST" },
  );
  if (!res.ok) await throwFriendly(res);
  return res.json() as Promise<IntegrationSyncResult>;
}
