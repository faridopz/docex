import type { Question } from "@/types";

/** Purpose category — drives grouping + iconography in the library. */
export type TemplateCategory =
  | "screen"
  | "reconcile"
  | "extract"
  | "compare";

export interface TemplateQuestion {
  text: string;
  // Optional hint that helps DOCex find the answer ("the budget total is
  // usually on the cover page or a summary table"). Per Google/Azure
  // Document AI research, per-field descriptions materially improve
  // extraction accuracy — this is a key edge over a one-off LLM prompt.
  hint?: string;
}

export interface QuestionTemplate {
  id: string;
  name: string;
  description: string;
  questions: TemplateQuestion[];   // ids generated at load time
  // Optional context paragraph shipped with the template. When the user
  // selects a template, this is offered as a starter for the context field
  // — telling DOCex how to interpret the documents (section structure,
  // funder vocabulary, etc.) without being a literal lookup key inside
  // any single question. Never auto-overwrites context the user has
  // already typed.
  defaultContext?: string;
  // Purpose category — optional on legacy/user templates.
  category?: TemplateCategory;
  // True for the built-in starters (locked, clonable). User-created
  // templates omit this. Set by the store, not authored here.
  starter?: boolean;
}

/**
 * STARTER_TEMPLATES — the curated, built-in templates every org begins
 * with. Users can duplicate any of these into an editable copy, or create
 * their own from scratch. The store (lib/template-store.ts) merges these
 * with the user's saved templates.
 */
export const STARTER_TEMPLATES: QuestionTemplate[] = [
  {
    id: "subaward-application-review",
    name: "Sub-award Application Review",
    category: "screen",
    description:
      "For reviewing applicant bundles (cost proposal, technical proposal, budget, workplan, M&E plan).",
    questions: [
      { text: "Is the proposal background clearly linked to the stated goals and objectives?" },
      { text: "Does the proposal describe the current state of the target geography (states, communities, beneficiaries)?" },
      { text: "Are both technical and strategic considerations addressed in the proposal?" },
      { text: "Is the proposed intervention sustainable beyond the funding period?" },
      { text: "Is the proposed intervention scalable to other states or programmes?" },
      { text: "Does the budget align with the activities described in the workplan?" },
      { text: "Does the M&E plan reflect the indicators and outputs mentioned in the technical proposal?" },
      { text: "Are all activities and outputs in the workplan costed in the budget?" },
      { text: "Does the workplan timeline match the proposed deliverables and milestones?" },
      { text: "What is the total budget requested?" },
      { text: "Are the M&E indicators specific, measurable, and time-bound?" },
      { text: "Is there evidence of prior donor funding management?" },
      { text: "Does the budget align with the activities specified in the workplan? (Cost Proposal + Workplan)" },
      { text: "Are the M&E indicators in the M&E plan consistent with the outputs described in the technical proposal? (M&E Plan + Technical Proposal)" },
      { text: "Does the workplan timeline match the deliverables proposed in the technical proposal? (Workplan + Technical Proposal)" },
      { text: "Are all activities in the workplan reflected as cost line items in the budget? (Workplan + Budget)" },
      { text: "Is the cost proposal consistent with the budget in total amount and category breakdown? (Cost Proposal + Budget)" },
    ],
  },
  {
    id: "financial-service-reconciliation",
    name: "Financial ↔ Service Reconciliation",
    category: "reconcile",
    description:
      "Cross-checks a partner's financial report against their service / programmatic report — flags activities without cost trace, costs without activity, and quantity or period mismatches.",
    // Why this template exists (Ed's recommendation from the demo):
    // Partners submit two reports per cycle — what they did (service) and
    // what they spent (financial). The audit-defensible question that's
    // brutal to answer manually is whether the two stories of the same
    // quarter agree. This template orchestrates the cross-document check
    // so DOCex surfaces inconsistencies; the human reviewer judges them.
    defaultContext:
      "This is a reconciliation review of one partner's reporting for a single period. Two reports are being compared together: (1) the SERVICE / PROGRAMMATIC REPORT, which describes what was done — activities, trainings, services delivered, beneficiaries reached, geographic coverage — and (2) the FINANCIAL REPORT, which describes what was spent — line items, amounts, categories, budget versus actuals. The reviewer wants to identify inconsistencies between the two stories of the same quarter: activities done without corresponding cost evidence, costs without corresponding activity, quantity or scope mismatches, period mismatches, and budget variance. Every cross-match answer should cite quotes from BOTH source documents where possible. DOCex is identifying inconsistencies — the human reviewer judges whether each one is benign or concerning. Never accuse, score, or make selection decisions.",
    questions: [
      { text: "List every distinct activity, training, output, or service delivery mentioned in the service / programmatic report. Include the quantity, scope, or geography for each where stated." },
      { text: "List every expenditure line item, cost category, or budget allocation in the financial report. Include the amount reported for each." },
      { text: "For each activity in the service report, identify the corresponding line item in the financial report. For each match, cite both the service report quote and the financial line item. Flag any activity that has no clear financial trace." },
      { text: "For each line item in the financial report, identify the corresponding activity in the service report. Flag any expenditure that has no documented activity in the service report." },
      { text: "Where the service and financial reports describe the same activity (e.g. trainings, workshops, distributions), do the quantities, locations, and dates align? Flag any inconsistency between the two sources." },
      { text: "What is the total expenditure reported in the financial report? What was the total budgeted amount? What is the variance (absolute and percentage) and is an explanation provided?" },
      { text: "Do both reports cover the same reporting period (same start and end dates)? Flag any period mismatch." },
      { text: "What is the burn rate (expenditure as a percentage of total budget) for this reporting period? Is the burn rate consistent with the activities reported as completed?" },
      { text: "Are there any costs in the financial report that do not correspond to a line item in the original workplan or proposal? (Only answerable if the workplan or proposal is also uploaded — flag if not.)" },
      { text: "Are there activities in the original workplan that do not appear in either the service report or the financial report? (Only answerable if the workplan or proposal is also uploaded — flag if not.)" },
    ],
  },
  {
    id: "invoice-receipt-extraction",
    name: "Invoice & Receipt Extraction",
    category: "extract",
    description:
      "Pull structured data from invoices and receipts — vendor, amount, dates, line items — into one row per document. Built for finance teams reconciling stacks of receipts at month-end.",
    // Finance teams typically need the same metadata fields off every
    // invoice or receipt: vendor identity, amounts, dates, line items,
    // and proof markers (signature, stamp, original/duplicate). Extracting
    // these into one row per document means the Excel export becomes a
    // ready-to-reconcile spreadsheet that finance can drop into their
    // existing GL workflow.
    defaultContext:
      "These are vendor invoices, payment receipts, or expense receipts. The goal is to extract structured metadata so finance can reconcile them against payment vouchers, budgets, and bank statements. One row per document in the output. If a field is genuinely missing from the document, mark it not_found rather than inferring — finance audits depend on knowing what's actually present versus what's been guessed.",
    questions: [
      { text: "What is the vendor or supplier name?" },
      { text: "What is the vendor's full address?" },
      { text: "What is the vendor's contact information (phone, email, tax ID where present)?" },
      { text: "What is the invoice or receipt number?" },
      { text: "What is the invoice or receipt date?" },
      { text: "What is the total amount, including any tax or VAT?" },
      { text: "What is the subtotal before tax?" },
      { text: "What is the tax or VAT amount, and what is the tax rate?" },
      { text: "What currency are the amounts in?" },
      { text: "List each line item with description, quantity, unit price, and line total." },
      { text: "What is the payment method (cash, bank transfer, cheque, card, or other)?" },
      { text: "If a payment due date or payment terms are specified, what are they?" },
      { text: "Is there a signature, stamp, or authorization mark on the document? If yes, whose name or title appears with it?" },
      { text: "Does the document indicate whether it is an ORIGINAL or a COPY/DUPLICATE? Look for stamps, watermarks, or text markings." },
      { text: "Is a purchase order number, contract reference, or budget code referenced on the document?" },
    ],
  },
  {
    id: "quarterly-report-review",
    name: "Quarterly Report Review",
    category: "screen",
    description:
      "For reviewing partner quarterly progress reports against targets and commitments.",
    // Section structure goes in the context, not in the questions themselves
    // — most TA Connect partners use a shared four-section template, but
    // CHAI and JHPIEGO use looser variants of the same content. Questions
    // that hard-code "Section C" return not_found on those partners even
    // when the answer is two pages away under a different heading. So we
    // tell Claude about the structure as a hint and keep the questions
    // content-focused.
    defaultContext:
      "These are quarterly progress reports from sub-awardee partners. Most partners use a shared four-section reporting template: Section A — Executive Summary, Section B — Programme Progress Update, Section C — Progress Towards Programme Targets, Section D — Risk Management. Other partners may use different section headings (Executive Summary / Background / Approach / Activities / Challenges / Lessons) but cover the same content. Use the section structure as a guide where it's present, but rely on the substance of the writing to locate answers when section names differ.",
    questions: [
      { text: "What does the report identify as the period's key achievements?" },
      { text: "What activities were completed during the reporting period? List each with its status (completed, partial, not started)." },
      { text: "Which states and Local Government Areas (LGAs) did the partner operate in this period?" },
      { text: "What stakeholder engagements, workshops, or coordination meetings did the partner participate in?" },
      { text: "What progress is reported against the programme targets or indicators? For each, include both the target and the actual figure where given." },
      { text: "Which targets were missed, and what reasons are given for any shortfalls?" },
      { text: "What major challenges, delays, or stop-work events were reported in the quarter?" },
      { text: "What risks does the report flag, and what mitigation is described for each?" },
      { text: "What lessons learned are documented?" },
      { text: "What activities are planned for the next quarter, including any carry-over items?" },
      { text: "Does the report include a financial summary? If yes, what is the total expenditure reported for the period?" },
      { text: "Who signed the report and on what date? Include name and title where given." },
    ],
  },
].map((t) => ({ ...t, starter: true }) as QuestionTemplate);

/**
 * Backwards-compatible alias. Older imports reference QUESTION_TEMPLATES;
 * new code should prefer the store (lib/template-store.ts) which merges
 * starters with the user's saved templates.
 */
export const QUESTION_TEMPLATES = STARTER_TEMPLATES;
