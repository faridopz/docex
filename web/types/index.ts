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
  // Routing/scope + the configurable approval chain (ordered stage labels).
  applies_to?: string[];
  org?: string | null;
  approval_workflow?: string[];
}

/** The organisation's config layer — how DOCex adapts to each client. */
export interface OrgProfile {
  name: string;
  roles: string[];
  default_approval_workflow: string[];
  directory: Record<string, string>; // stage/role -> email
  updated_at?: string | null;
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
  // Requisition metadata — Day 14. Optional context an officer captures
  // when uploading a check that mirrors the paper requisition form TA
  // Connect (and friends) currently route through email.
  requisition_date?: string | null;
  billing_donor?: string | null;
  payment_purpose?: string | null;
  items_requested?: string | null;
  requested_by?: string | null;
  approved_by?: string | null;
  // Approval-chain state — Day 14. pending_with is whoever the check is
  // sitting with right now (free-text, name or email). pending_question
  // is the outstanding clarification (if any). Both clear on responder
  // action.
  pending_with?: string | null;
  pending_question?: string | null;
  // Snapshot of the active rules at check time. Frozen on first save so
  // later rulebook edits never alter historical audit trails.
  rulebook_snapshot_rules?: PolicyRule[] | null;
  // Append-only human decision log. Every officer action on this check
  // lands here with a timestamp + (eventually) actor + reason. This is the
  // audit-trail surface an auditor actually asks for: "what did your team
  // do about this flag, and when, and why?"
  decision_log?: DecisionEvent[];
  risks?: RiskEntry[];
}

export type RiskSeverity = "high" | "medium" | "low";
export type RiskStatus = "open" | "in_progress" | "resolved";

/** A risk the officer identified on a check and how it was handled. */
export interface RiskEntry {
  id: string;
  created_at: string;
  description: string;
  severity: RiskSeverity;
  action_taken?: string | null;
  escalated: boolean;
  escalated_to?: string | null;
  action_plan?: string | null;
  status: RiskStatus;
  resolved_at?: string | null;
  author?: string | null;
  related_rule_id?: string | null;
  updated_at?: string | null;
}

export type DecisionEventType =
  | "check_run"
  | "note_added"
  | "rule_dismissed"
  | "rule_escalated"
  | "clarification_requested"
  | "clarification_received"
  | "escalated"
  | "approved"
  | "unapproved"
  | "risk_identified"
  | "risk_updated"
  | "risk_resolved";

export interface DecisionEvent {
  type: DecisionEventType;
  timestamp: string;
  actor: string | null;
  note: string | null;
  rule_id: string | null;
  rule_description: string | null;
  // Signature — Day 15. Optional drawn signature + typed name. Approve,
  // escalate, and final clarification responses are the typical signed
  // events. Notes / dismissals usually skip the pad.
  signature_data_url?: string | null;
  signed_name?: string | null;
  // Sprint 2 — when an escalation/clarification was emailed to the
  // responsible party, the address it went to. Null if no email was sent.
  notified_email?: string | null;
  // Audit-grade provenance: how the action was taken + where from.
  source?: string | null; // "in-app" | "email-verified" | "system"
  ip?: string | null;
}

export interface AuditLogRow {
  timestamp: string | null;
  check_id: string;
  payment_label: string;
  rulebook_name: string;
  event: string;
  actor: string | null;
  detail: string | null;
  rule: string | null;
  signed_name: string | null;
  notified_email: string | null;
  source: string | null;
  ip: string | null;
}

// Human-friendly labels + colour tokens for the timeline UI.
export const decisionEventLabel: Record<DecisionEventType, string> = {
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

export const decisionEventColor: Record<DecisionEventType, string> = {
  check_run: "bg-gray-100 text-gray-700 ring-1 ring-gray-200",
  note_added: "bg-sky-50 text-sky-700 ring-1 ring-sky-200",
  rule_dismissed: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  rule_escalated: "bg-violet-50 text-violet-700 ring-1 ring-violet-200",
  clarification_requested: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  clarification_received: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200",
  escalated: "bg-violet-50 text-violet-700 ring-1 ring-violet-200",
  approved: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  unapproved: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

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
  pending_with?: string | null;
  pending_question?: string | null;
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

// ── Bank Verify ──────────────────────────────────────────────────────────
//
// Bank Verify is the third DOCex primitive — alongside Extraction and
// Compliance Check. Mirrors models.py / api/schemas.py. Field names must
// stay in sync across all three.
//
// Bank Verify is a standalone tool (anyone can drop accounts in and verify
// them, no agent context required) AND a composable step inside larger
// agents (Attendance Payment Co-Pilot, Sub-award Co-Pilot, Procurement Agent).
// The 'purpose' field captures WHY the verification ran so the audit trail
// stays meaningful and notifications route to the right person.

export type BankVerifyVerdict =
  | "verified"
  | "warning"
  | "mismatch"
  | "unverifiable";

export interface BankVerifyResult {
  recipient_name: string;
  account_number: string;
  bank_code: string;
  bank_name: string | null;
  resolved_name: string | null;
  verdict: BankVerifyVerdict;
  match_score: number | null;
  error_message: string | null;
  timestamp: string | null;
  amount: number | null;
  notes: string | null;
}

export interface BankVerifyBatchResult {
  total: number;
  verified: number;
  warning: number;
  mismatch: number;
  unverifiable: number;
  results: BankVerifyResult[];
  batch_id: string | null;
  source_schedule: string | null;
  created_at: string | null;
  purpose: string | null;
  purpose_detail: string | null;
}

export interface BatchVerifySummary {
  batch_id: string;
  source_schedule: string | null;
  purpose: string | null;
  purpose_detail: string | null;
  total: number;
  verified: number;
  warning: number;
  mismatch: number;
  unverifiable: number;
  created_at: string | null;
}

export interface BatchVerifyListResponse {
  batches: BatchVerifySummary[];
}

// ── Verify display tokens ────────────────────────────────────────────────
//
// Same vocabulary as confidenceColor / verdictColor — emerald/amber/rose/
// gray for the four verdict bands. Keeping the palette consistent across
// every DOCex primitive means an officer who learns one screen can read
// any other screen without re-training their eye.

export const bankVerdictLabel: Record<BankVerifyVerdict, string> = {
  verified: "Verified",
  warning: "Warning",
  mismatch: "Mismatch",
  unverifiable: "Unverifiable",
};

export const bankVerdictColor: Record<BankVerifyVerdict, string> = {
  verified: "text-emerald-700 bg-emerald-50 border-emerald-200",
  warning: "text-amber-700 bg-amber-50 border-amber-200",
  mismatch: "text-rose-700 bg-rose-50 border-rose-200",
  unverifiable: "text-gray-600 bg-gray-50 border-gray-200",
};

export const bankVerdictRing: Record<BankVerifyVerdict, string> = {
  verified: "ring-1 ring-emerald-200",
  warning: "ring-1 ring-amber-200",
  mismatch: "ring-1 ring-rose-200",
  unverifiable: "ring-1 ring-gray-200",
};

export const bankVerdictDot: Record<BankVerifyVerdict, string> = {
  verified: "bg-emerald-500",
  warning: "bg-amber-400",
  mismatch: "bg-rose-500",
  unverifiable: "bg-gray-300",
};

// ── Purpose taxonomy ─────────────────────────────────────────────────────
//
// The 'why' of a verification batch. Standard values offered as buttons
// in the UI; 'other' opens a free-text field for custom purposes.

export type StandardPurpose =
  | "event_payment"
  | "grantee_disbursement"
  | "vendor_payment"
  | "partner_reimbursement"
  | "other";

export const purposeLabel: Record<StandardPurpose, string> = {
  event_payment: "Event payment",
  grantee_disbursement: "Grantee disbursement",
  vendor_payment: "Vendor payment",
  partner_reimbursement: "Partner reimbursement",
  other: "Other",
};

export const purposeDescription: Record<StandardPurpose, string> = {
  event_payment: "Per-diems and honoraria for training or workshop attendees",
  grantee_disbursement: "Payout to a sub-award partner after their grant is awarded",
  vendor_payment: "Payment to a procurement vendor for goods or services",
  partner_reimbursement: "Reimbursing a partner organisation for an agreed expense",
  other: "Anything else — describe the purpose in your own words",
};

// ── Attendance Payment Co-Pilot ─────────────────────────────────────────────
//
// DOCex's first *composite* agent — chains parse-attendance, parse-payment-
// info, fuzzy-match, calculate-amounts, hand-off-to-bank-verify. Targets
// the Programs team's end-to-end pain of paying event attendees.

export type AttendeeStatus = "paid" | "no_attendance" | "no_payment_info";

export interface MatchedAttendee {
  payment_info_name: string | null;
  attendance_name: string | null;
  match_score: number | null;
  status: AttendeeStatus;
  days_attended: number;
  day_labels: string[];
  organisation: string | null;
  account_number: string | null;
  bank_code: string | null;
  bank_name: string | null;
  role: string | null;
  applied_rate_per_day: number;
  amount: number;
}

export interface AttendancePaymentRun {
  event_name: string;
  rate_per_day: number;
  days_in_event: number;
  matched: MatchedAttendee[];
  no_attendance: MatchedAttendee[];
  no_payment_info: MatchedAttendee[];
  total_to_pay: number;
  paid_count: number;
  no_attendance_count: number;
  no_payment_info_count: number;
  run_id: string | null;
  created_at: string | null;
  attendance_filename: string | null;
  payment_info_filename: string | null;
  bank_verify_batch_id: string | null;
  rate_card_id: string | null;
  rate_card_name: string | null;
  rate_card_snapshot: RateCard | null;
  accuracy_flags: string[];
  attendance_source: "xlsx" | "google_sheets" | "collection";
  payment_info_source: "xlsx" | "google_sheets" | "collection";
}

export interface AttendancePaymentRunSummary {
  run_id: string;
  event_name: string;
  rate_per_day: number;
  days_in_event: number;
  paid_count: number;
  no_attendance_count: number;
  no_payment_info_count: number;
  total_to_pay: number;
  created_at: string | null;
  attendance_filename: string | null;
  payment_info_filename: string | null;
  bank_verify_batch_id: string | null;
}

// ─── Attendance Collections (native intake + self-check-in) ─────────────────

export interface CollectedAttendee {
  id: string;
  name: string;
  organisation?: string | null;
  account_number: string;
  bank_code: string;
  bank_name?: string | null;
  role?: string | null;
  present_days: string[];
  source: "organizer" | "self";
}

export interface AttendanceCollection {
  id: string;
  event_name: string;
  day_labels: string[];
  rate_per_day: number;
  rate_card_id?: string | null;
  share_token: string;
  created_at?: string | null;
  attendees: CollectedAttendee[];
  run_id?: string | null;
}

export interface AttendanceCollectionSummary {
  id: string;
  event_name: string;
  attendee_count: number;
  day_count: number;
  created_at?: string | null;
  run_id?: string | null;
}

export interface PublicCollectionInfo {
  event_name: string;
  day_labels: string[];
  already_submitted: number;
}

export const attendeeStatusLabel: Record<AttendeeStatus, string> = {
  paid: "Paid",
  no_attendance: "No attendance",
  no_payment_info: "No bank info",
};

export const attendeeStatusColor: Record<AttendeeStatus, string> = {
  paid: "text-emerald-700 bg-emerald-50 border-emerald-200",
  no_attendance: "text-rose-700 bg-rose-50 border-rose-200",
  no_payment_info: "text-amber-700 bg-amber-50 border-amber-200",
};

export const attendeeStatusDot: Record<AttendeeStatus, string> = {
  paid: "bg-emerald-500",
  no_attendance: "bg-rose-500",
  no_payment_info: "bg-amber-400",
};

// ── Knowledge Hub ────────────────────────────────────────────────────────
//
// Slide-deck ingestion + chat. The fifth DOCex primitive. Mirrors the
// SlideDeck / Slide / KnowledgeAnswer Pydantic models exactly.

export interface Slide {
  number: number;
  title: string | null;
  body: string[];
  speaker_notes: string | null;
  table_text: string[];
}

// Document type drives the chunk vocabulary ("Slide N" / "Page N" / "Section N")
// and the badge shown on each document card.
export type DocumentContentType = "pptx" | "docx" | "pdf";

export interface SlideDeck {
  id: string;
  name: string;
  source_filename: string;
  content_type: DocumentContentType;
  slide_count: number;
  slides: Slide[];
  tags: string[];
  description: string | null;
  // Slash-delimited folder path. null = root level. "Reports/2026/Q1"
  // renders as a 3-deep tree in the library sidebar.
  folder: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SlideDeckSummary {
  id: string;
  name: string;
  source_filename: string;
  content_type: DocumentContentType;
  slide_count: number;
  tags: string[];
  description: string | null;
  folder: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// The label shown for one chunk of a doc — used in citation chips, the
// slide list header, the empty-chat example questions, etc. Keep this
// in sync with the backend chunk_label_for() helper in slides.py.
export const chunkLabel: Record<DocumentContentType, string> = {
  pptx: "Slide",
  docx: "Section",
  pdf: "Page",
};

export const chunkLabelPlural: Record<DocumentContentType, string> = {
  pptx: "slides",
  docx: "sections",
  pdf: "pages",
};

// Format badge styling for the document cards.
export const contentTypeBadge: Record<DocumentContentType, string> = {
  pptx: "bg-orange-50 text-orange-700 ring-1 ring-orange-200",
  docx: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  pdf: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

export const contentTypeLabel: Record<DocumentContentType, string> = {
  pptx: "PowerPoint",
  docx: "Word",
  pdf: "PDF",
};

export interface SlideCitation {
  slide_number: number;
  excerpt: string | null;
  // Set for library-wide citations so the chip can deep-link to the right
  // document. Null for per-document chat where the deck context is implicit.
  deck_id: string | null;
  deck_name: string | null;
}

export interface KnowledgeAnswer {
  question: string;
  answer: string;
  citations: SlideCitation[];
  deck_id: string;
  deck_name: string;
  error: string | null;
  created_at: string | null;
  // Library-wide chat only: documents skipped because the library
  // exceeded Claude's context budget. Empty for per-document chat.
  truncated_decks?: string[];
}

// ── DOCex Assistant ──────────────────────────────────────────────────────
//
// The agentic narrator. Every result page renders an AssistantBrief at the
// top — Claude's plain-English summary of what just happened plus 0-5
// suggested next actions.

export type SuggestedActionUrgency = "high" | "medium" | "low";

export interface SuggestedAction {
  label: string;
  urgency: SuggestedActionUrgency;
  reason: string | null;
}

export interface AssistantBrief {
  narrative: string;
  actions: SuggestedAction[];
  headline: string | null;
  context_kind: string;
  context_id: string | null;
}

export const urgencyColor: Record<SuggestedActionUrgency, string> = {
  high: "bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100",
  medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-200 hover:bg-amber-100",
  low: "bg-gray-50 text-gray-700 ring-1 ring-gray-200 hover:bg-gray-100",
};

export const urgencyDot: Record<SuggestedActionUrgency, string> = {
  high: "bg-rose-500",
  medium: "bg-amber-400",
  low: "bg-gray-400",
};

// ── Self-Check Agent ─────────────────────────────────────────────────────
//
// Runtime diagnostic. V1 of the longer-term Self-Improvement Agent.

export type CheckStatus = "pass" | "warn" | "fail" | "skip";
export type DiagnosticOverall = "healthy" | "degraded" | "broken";

export interface CheckResult {
  id: string;
  category: string;
  title: string;
  status: CheckStatus;
  summary: string;
  evidence: string | null;
  fix_hint: string | null;
  duration_ms: number;
}

export interface DiagnosticReport {
  started_at: string;
  finished_at: string;
  duration_ms: number;
  total: number;
  passed: number;
  warned: number;
  failed: number;
  skipped: number;
  overall: DiagnosticOverall;
  checks: CheckResult[];
  report_id: string | null;
}

export interface DiagnosticReportSummary {
  report_id: string;
  started_at: string;
  duration_ms: number;
  overall: DiagnosticOverall;
  total: number;
  passed: number;
  warned: number;
  failed: number;
  skipped: number;
}

export const checkStatusColor: Record<CheckStatus, string> = {
  pass: "text-emerald-700 bg-emerald-50 border-emerald-200",
  warn: "text-amber-700 bg-amber-50 border-amber-200",
  fail: "text-rose-700 bg-rose-50 border-rose-200",
  skip: "text-gray-500 bg-gray-50 border-gray-200",
};

export const checkStatusDot: Record<CheckStatus, string> = {
  pass: "bg-emerald-500",
  warn: "bg-amber-400",
  fail: "bg-rose-500",
  skip: "bg-gray-300",
};

export const checkStatusIcon: Record<CheckStatus, string> = {
  pass: "✓",
  warn: "!",
  fail: "✗",
  skip: "·",
};

export const overallColor: Record<DiagnosticOverall, string> = {
  healthy: "text-emerald-800 bg-emerald-50 ring-1 ring-emerald-200",
  degraded: "text-amber-800 bg-amber-50 ring-1 ring-amber-200",
  broken: "text-rose-800 bg-rose-50 ring-1 ring-rose-200",
};

// ── Rate cards ───────────────────────────────────────────────────────────
//
// Reusable per-diem schedules. One default rate + per-role overrides.
// Agents consult a card at run time to compute amounts.

export interface RateLine {
  role: string;
  amount_per_day: number;
}

export interface RateCard {
  id: string;
  name: string;
  default_rate_per_day: number;
  roles: RateLine[];
  currency: string;
  created_at: string | null;
  updated_at: string | null;
}

// Extended MatchedAttendee + AttendancePaymentRun fields — kept on the
// originals above as optional. Re-export with the new fields documented
// so consumers can rely on the shape. (TS structural typing means we
// don't have to re-declare; this comment is for human readers.)
//
// MatchedAttendee.role: string | null
// MatchedAttendee.applied_rate_per_day: number
// AttendancePaymentRun.rate_card_id: string | null
// AttendancePaymentRun.rate_card_name: string | null
// AttendancePaymentRun.rate_card_snapshot: RateCard | null
// AttendancePaymentRun.accuracy_flags: string[]
// AttendancePaymentRun.attendance_source: "xlsx" | "google_sheets"
// AttendancePaymentRun.payment_info_source: "xlsx" | "google_sheets"
