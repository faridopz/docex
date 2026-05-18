import type { Question } from "@/types";

export interface QuestionTemplate {
  id: string;
  name: string;
  description: string;
  questions: { text: string }[];   // ids generated at load time
  // Optional context paragraph shipped with the template. When the user
  // selects a template, this is offered as a starter for the context field
  // — telling DOCex how to interpret the documents (section structure,
  // funder vocabulary, etc.) without being a literal lookup key inside
  // any single question. Never auto-overwrites context the user has
  // already typed.
  defaultContext?: string;
}

export const QUESTION_TEMPLATES: QuestionTemplate[] = [
  {
    id: "subaward-application-review",
    name: "Sub-award Application Review",
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
    id: "quarterly-report-review",
    name: "Quarterly Report Review",
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
];
