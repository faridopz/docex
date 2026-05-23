/**
 * Workflow-aware copy for the DOCex flow.
 *
 * The same UI flow is used for several review workflows — partner application
 * screening, quarterly report review, sub-award proposal review. The user
 * picks a template in Step 1; from then on the language across the wizard
 * adapts ("applicant" vs "report" vs "application", "Run review" vs
 * "Analyse reports" vs "Review applications").
 *
 * Keep all workflow-specific copy in this one file. Components import
 * getWorkflowLabels(templateId) and read whatever they need — no inline
 * conditionals on templateId in component files.
 */

export interface WorkflowLabels {
  // Singular/plural unit name (the thing being reviewed)
  unitSingular: string;
  unitPlural: string;
  unitSingularCapital: string;
  unitPluralCapital: string;

  // Action verbs
  actionVerb: string;       // imperative for buttons ("Run review", "Analyse")
  actionVerbPast: string;   // past tense for summaries ("Reviewed", "Analysed")

  // Step bar
  step2Label: string;       // "Add applicants" | "Add reports"

  // Step 2 — upload page
  uploadHeader: string;
  uploadDescription: string;
  singleGuidanceTitle: string;
  singleGuidanceBody: string;
  batchGuidanceTitle: string;
  batchGuidanceBody: string;
  singleModeLabel: string;
  batchModeLabel: string;
  unitNamePlaceholder: string;
  addUnitButton: string;
  emptyBatchHint: string;

  // Step 2 → 3
  stepTwoButton: string;
  stepThreeLoadingTitle: string;

  // Step 3 — results
  pageHeader: string;
  sidebarHeader: string;
}

const DEFAULT: WorkflowLabels = {
  unitSingular: "applicant",
  unitPlural: "applicants",
  unitSingularCapital: "Applicant",
  unitPluralCapital: "Applicants",
  actionVerb: "Run review",
  actionVerbPast: "Reviewed",

  step2Label: "Add applicants",

  uploadHeader: "Upload documents",
  uploadDescription:
    "Drop in everything submitted for one applicant. DOCex reads them together.",
  singleGuidanceTitle: "What to upload",
  singleGuidanceBody:
    "Drop in every document the applicant submitted in one go. DOCex reads the full bundle together so an answer found in one document can be cross-checked against the others.",
  batchGuidanceTitle: "How batch mode works",
  batchGuidanceBody:
    "Add each applicant and drop in their full document bundle. DOCex reviews every organisation against your questions and returns one row per applicant — built for side-by-side comparison.",
  singleModeLabel: "One applicant",
  batchModeLabel: "Batch",
  unitNamePlaceholder: "Applicant name",
  addUnitButton: "Add applicant",
  emptyBatchHint: "No applicants yet. Add the first one to get started.",

  stepTwoButton: "Run review",
  stepThreeLoadingTitle: "Reading documents…",

  pageHeader: "Review results",
  sidebarHeader: "Applicants",
};

const QUARTERLY_REPORT: WorkflowLabels = {
  unitSingular: "report",
  unitPlural: "reports",
  unitSingularCapital: "Report",
  unitPluralCapital: "Reports",
  actionVerb: "Analyse",
  actionVerbPast: "Analysed",

  step2Label: "Add reports",

  uploadHeader: "Upload partner reports",
  uploadDescription:
    "Drop in the quarterly progress report. DOCex extracts answers to your questions with the source quote and page.",
  singleGuidanceTitle: "What to upload",
  singleGuidanceBody:
    "Drop in the partner's quarterly progress report — narrative, tables, financial summary, all in one file. DOCex reads the full document and pulls structured answers to your questions, with the exact quote and page for each.",
  batchGuidanceTitle: "Reviewing several partners at once",
  batchGuidanceBody:
    "Add each partner and drop in their quarterly report. DOCex reads each one against your questions and returns a comparison view — one row per partner. Useful for reviewing the whole portfolio in one sitting.",
  singleModeLabel: "One report",
  batchModeLabel: "Many partners",
  unitNamePlaceholder: "Partner name (e.g. CHAI, CIHP, Pathfinder)",
  addUnitButton: "Add partner",
  emptyBatchHint: "No reports yet. Add the first partner to get started.",

  stepTwoButton: "Analyse reports",
  stepThreeLoadingTitle: "Reading reports…",

  pageHeader: "Report analysis",
  sidebarHeader: "Reports",
};

const SUBAWARD_APPLICATION: WorkflowLabels = {
  unitSingular: "application",
  unitPlural: "applications",
  unitSingularCapital: "Application",
  unitPluralCapital: "Applications",
  actionVerb: "Review",
  actionVerbPast: "Reviewed",

  step2Label: "Add applications",

  uploadHeader: "Upload applications",
  uploadDescription:
    "Drop in everything the applicant submitted — cost proposal, technical proposal, budget, workplan, M&E plan. DOCex reads them together.",
  singleGuidanceTitle: "What to upload",
  singleGuidanceBody:
    "Drop in the full application bundle — cost proposal, technical proposal, budget, workplan, M&E plan. DOCex reads everything together so it can check cross-document consistency (does the workplan match the budget? does the M&E plan match the proposal?).",
  batchGuidanceTitle: "Reviewing many applicants at once",
  batchGuidanceBody:
    "Add each applicant and drop in their full bundle. DOCex reviews every application against your questions and returns one row per applicant — built for side-by-side shortlisting.",
  singleModeLabel: "One applicant",
  batchModeLabel: "Batch",
  unitNamePlaceholder: "Applicant organisation name",
  addUnitButton: "Add applicant",
  emptyBatchHint: "No applicants yet. Add the first one to get started.",

  stepTwoButton: "Review applications",
  stepThreeLoadingTitle: "Reading applications…",

  pageHeader: "Application review",
  sidebarHeader: "Applicants",
};

const FINANCIAL_SERVICE_RECONCILIATION: WorkflowLabels = {
  unitSingular: "partner",
  unitPlural: "partners",
  unitSingularCapital: "Partner",
  unitPluralCapital: "Partners",
  actionVerb: "Reconcile",
  actionVerbPast: "Reconciled",

  step2Label: "Add partners",

  uploadHeader: "Upload reports to reconcile",
  uploadDescription:
    "For each partner, drop in the financial report AND the service / programmatic report for the same period. DOCex reads them together and flags inconsistencies.",
  singleGuidanceTitle: "What to upload",
  singleGuidanceBody:
    "Drop in BOTH the financial report and the service / programmatic report for the same partner and same period. DOCex compares the two to surface activities without cost trace, costs without activity, quantity mismatches, and budget variance. Optionally add the partner's workplan or proposal — this enables additional checks on unauthorised costs and missing activities.",
  batchGuidanceTitle: "Reconciling multiple partners at once",
  batchGuidanceBody:
    "Add each partner and drop in BOTH their financial and service report (plus the workplan if you want the deeper checks). DOCex runs the reconciliation across all partners and returns one row per partner — useful for portfolio-wide audit prep.",
  singleModeLabel: "One partner",
  batchModeLabel: "Many partners",
  unitNamePlaceholder: "Partner name (e.g. CHAI, CIHP, Pathfinder)",
  addUnitButton: "Add partner",
  emptyBatchHint: "No partners yet. Add the first one to get started.",

  stepTwoButton: "Run reconciliation",
  stepThreeLoadingTitle: "Reconciling reports…",

  pageHeader: "Reconciliation results",
  sidebarHeader: "Partners",
};

const INVOICE_RECEIPT: WorkflowLabels = {
  unitSingular: "invoice",
  unitPlural: "invoices",
  unitSingularCapital: "Invoice",
  unitPluralCapital: "Invoices",
  actionVerb: "Extract",
  actionVerbPast: "Extracted",

  step2Label: "Add invoices",

  uploadHeader: "Upload invoices and receipts",
  uploadDescription:
    "Drop in invoices, receipts, or expense vouchers. DOCex pulls vendor info, amounts, dates, and line items — one row per document.",
  singleGuidanceTitle: "What to upload",
  singleGuidanceBody:
    "Drop in one or more invoices or receipts for the same expense. DOCex extracts the structured fields (vendor, amounts, dates, line items) and you get a clean answer set you can paste straight into your finance spreadsheet.",
  batchGuidanceTitle: "Processing many invoices at once",
  batchGuidanceBody:
    "Add each invoice or receipt bundle and drop in its documents. DOCex extracts the fields from each and returns one row per bundle in the Excel export — built for finance teams reconciling stacks at month-end.",
  singleModeLabel: "One invoice",
  batchModeLabel: "Many invoices",
  unitNamePlaceholder: "Label (e.g. INV-2025-04-17 or Vendor X — Office Supplies)",
  addUnitButton: "Add invoice",
  emptyBatchHint: "No invoices yet. Add the first one to get started.",

  stepTwoButton: "Extract data",
  stepThreeLoadingTitle: "Reading invoices…",

  pageHeader: "Invoice data",
  sidebarHeader: "Invoices",
};

export function getWorkflowLabels(
  templateId: string | null | undefined,
): WorkflowLabels {
  if (templateId === "quarterly-report-review") return QUARTERLY_REPORT;
  if (templateId === "subaward-application-review") return SUBAWARD_APPLICATION;
  if (templateId === "financial-service-reconciliation")
    return FINANCIAL_SERVICE_RECONCILIATION;
  if (templateId === "invoice-receipt-extraction") return INVOICE_RECEIPT;
  return DEFAULT;
}
