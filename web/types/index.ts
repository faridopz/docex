// ── Questions ─────────────────────────────────────────────────────────────────

export interface Question {
  id: string;
  text: string; // plain language, e.g. "What states does this org work in?"
}

// ── Extraction answers ────────────────────────────────────────────────────────

export type Confidence = "found" | "inferred" | "not_found";

export interface ExtractionAnswer {
  question_id: string;
  question_text: string;
  answer: string | null;           // null when not_found
  confidence: Confidence;
  source_document: string | null;  // filename the answer came from
  source_page: number | null;      // page number from PDF (null for DOCX/TXT)
  quote: string | null;            // verbatim excerpt from the document
  search_notes: string | null;     // reasoning trail for inferred/not_found answers
}

// ── Single applicant result ───────────────────────────────────────────────────

export interface SingleExtractionResponse {
  applicant_name: string;
  documents: string[];             // list of filenames that were read
  answers: ExtractionAnswer[];
  error?: string | null;
}

// ── Batch result ──────────────────────────────────────────────────────────────

export interface ApplicantExtraction {
  applicant_id: string;
  applicant_name: string;
  documents: string[];
  answers: ExtractionAnswer[];
  error?: string | null;
}

export interface BatchExtractionResponse {
  total: number;
  succeeded: number;
  failed: number;
  applicants: ApplicantExtraction[];
}

// ── UI state — applicant being assembled before submission ────────────────────

export interface ApplicantInput {
  id: string;
  name: string;
  files: File[];
}

// ── Confidence display helpers ────────────────────────────────────────────────

export const confidenceLabel: Record<Confidence, string> = {
  found: "Found",
  inferred: "Inferred",
  not_found: "Not found",
};

export const confidenceColor: Record<Confidence, string> = {
  found: "text-emerald-700 bg-emerald-50 border-emerald-200",
  inferred: "text-amber-700 bg-amber-50 border-amber-200",
  not_found: "text-gray-500 bg-gray-50 border-gray-200",
};

export const confidenceDot: Record<Confidence, string> = {
  found: "bg-emerald-500",
  inferred: "bg-amber-400",
  not_found: "bg-gray-300",
};

// ── Compliance ────────────────────────────────────────────────────────────
//
// Compliance Check is the second DOCex primitive — alongside Extraction.
// Models mirror models.py at the project root. Field names must stay in sync.

export type RuleCategory =
  | "procurement"
  | "receipts"
  | "approvals"
  | "vendor"
  | "advance"
  | "retirement"
  | "documentation"
  | "general";

export interface PolicyRule {
  id: string;
  clause_reference: string | null;
  description: string;
  condition: string | null;
  evidence_required: string[];
  category: RuleCategory | null;
  source_quote: string | null;
  source_page: number | null;
  active: boolean;
}

export type NotificationTrigger =
  | "always"
  | "flagged_or_blocked"
  | "blocked_only";

export interface PolicyRulebook {
  id: string;
  name: string;
  source_documents: string[];
  rules: PolicyRule[];
  interpretation_notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Notifications — opt-in per rulebook. When email is set + trigger
  // matches a check's verdict, DOCex sends an alert email. Configured
  // in the rulebook editor; requires backend SMTP env vars to actually fire.
  notification_email?: string | null;
  notification_trigger?: NotificationTrigger | null;
}

export interface RulebookSummary {
  id: string;
  name: string;
  rule_count: number;
  active_rule_count: number;
  source_documents: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface RulebookListResponse {
  rulebooks: RulebookSummary[];
}

export type RuleVerdict =
  | "pass"
  | "flag"
  | "block"
  | "not_applicable"
  | "insufficient_evidence";

export type OverallVerdict = "approved" | "flagged" | "blocked";

export interface RuleResult {
  rule_id: string;
  rule_description: string;
  verdict: RuleVerdict;
  reasoning: string;
  policy_citation: string | null;
  payment_evidence: string | null;
  missing_evidence: string[];
  applied_to_document: string | null;
  confidence: Confidence;
}

export interface ComplianceCheckResult {
  payment_id: string;
  payment_label: string;
  documents: string[];
  rulebook_id: string;
  rulebook_name: string;
  overall_verdict: OverallVerdict;
  overall_summary: string;
  results: RuleResult[];
  error?: string | null;
  // Persistence + audit metadata — populated server-side on save
  created_at?: string | null;
  approved?: boolean;
  approved_at?: string | null;
  // Snapshot of the active rules at check time. Frozen on first save so
  // later rulebook edits never alter historical audit trails.
  rulebook_snapshot_rules?: PolicyRule[] | null;
}

export interface CheckSummary {
  payment_id: string;
  payment_label: string;
  rulebook_id: string;
  rulebook_name: string;
  overall_verdict: OverallVerdict;
  overall_summary: string;
  document_count: number;
  created_at?: string | null;
  approved?: boolean;
  approved_at?: string | null;
  error?: string | null;
}

export interface CheckListResponse {
  checks: CheckSummary[];
}

export interface ComplianceCheckBatchResult {
  total: number;
  approved: number;
  flagged: number;
  blocked: number;
  checks: ComplianceCheckResult[];
}

// ── Verdict display ───────────────────────────────────────────────────────
//
// Mirrors the confidenceLabel/Color/Dot pattern. Designed so "pass" sits
// visually alongside "found" (both emerald) and "block" reads with the
// same urgency as the rose-tinted "major-gaps" bucket. New token: sky for
// "insufficient_evidence" — actionable signal, distinct from gray "not_found"
// (which reads as a dead end).
//
// Copy choice — "Need info" over "Insufficient evidence" reduces anxiety:
// it tells the officer what to do next ("get the info") rather than that
// they failed.

export const verdictLabel: Record<RuleVerdict, string> = {
  pass: "Pass",
  flag: "Flag",
  block: "Block",
  not_applicable: "N/A",
  insufficient_evidence: "Need info",
};

export const verdictColor: Record<RuleVerdict, string> = {
  pass: "text-emerald-700 bg-emerald-50 border-emerald-200",
  flag: "text-amber-700 bg-amber-50 border-amber-200",
  block: "text-rose-700 bg-rose-50 border-rose-200",
  not_applicable: "text-gray-500 bg-gray-50 border-gray-200",
  insufficient_evidence: "text-sky-700 bg-sky-50 border-sky-200",
};

export const verdictDot: Record<RuleVerdict, string> = {
  pass: "bg-emerald-500",
  flag: "bg-amber-400",
  block: "bg-rose-500",
  not_applicable: "bg-gray-300",
  insufficient_evidence: "bg-sky-500",
};

export const overallVerdictLabel: Record<OverallVerdict, string> = {
  approved: "Approved",
  flagged: "Flagged",
  blocked: "Blocked",
};

export const overallVerdictColor: Record<OverallVerdict, string> = {
  approved: "text-emerald-800 bg-emerald-50 ring-1 ring-emerald-200",
  flagged: "text-amber-800 bg-amber-50 ring-1 ring-amber-200",
  blocked: "text-rose-800 bg-rose-50 ring-1 ring-rose-200",
};

export const overallVerdictDot: Record<OverallVerdict, string> = {
  approved: "bg-emerald-500",
  flagged: "bg-amber-400",
  blocked: "bg-rose-500",
};

// ── Rule categories ──────────────────────────────────────────────────────
//
// Each rule belongs to one category. The editor groups rules by category
// so a 40-rule policy reads as 6-7 chunks of 5-7 rules each — manageable
// chunks per Miller's law. Distinct per-category pill colours help the
// officer's eye land on the right group without reading every header.

export const categoryLabel: Record<RuleCategory, string> = {
  procurement: "Procurement",
  receipts: "Receipts",
  approvals: "Approvals",
  vendor: "Vendor",
  advance: "Advance",
  retirement: "Retirement",
  documentation: "Documentation",
  general: "General",
};

export const categoryColor: Record<RuleCategory, string> = {
  procurement: "bg-violet-50 text-violet-700 ring-1 ring-violet-200",
  receipts: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  approvals: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  vendor: "bg-orange-50 text-orange-700 ring-1 ring-orange-200",
  advance: "bg-pink-50 text-pink-700 ring-1 ring-pink-200",
  retirement: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  documentation: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
  general: "bg-gray-50 text-gray-700 ring-1 ring-gray-200",
};
