import type {
  ApplicantExtraction,
  ApplicantInput,
  BatchExtractionResponse,
  CheckListResponse,
  CheckSummary,
  ComplianceCheckBatchResult,
  ComplianceCheckResult,
  PolicyRule,
  PolicyRulebook,
  Question,
  RulebookListResponse,
  RulebookSummary,
  SingleExtractionResponse,
} from "@/types";
import { assignBucket } from "@/lib/buckets";

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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to draft follow-up notes: ${detail}`);
  }
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

export async function approveCheck(id: string): Promise<ComplianceCheckResult> {
  const res = await fetch(
    `${BASE}/compliance/checks/${encodeURIComponent(id)}/approve`,
    { method: "POST" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to approve check (${res.status}): ${detail}`);
  }
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
