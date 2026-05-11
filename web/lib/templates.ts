import type { Question } from "@/types";

export interface QuestionTemplate {
  id: string;
  name: string;
  description: string;
  questions: { text: string }[];   // ids generated at load time
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
    ],
  },
  {
    id: "quarterly-report-review",
    name: "Quarterly Report Review",
    description:
      "For reviewing partner quarterly progress reports against targets and commitments.",
    questions: [
      { text: "Did the partner meet their key activity targets this quarter?" },
      { text: "What were the major challenges or delays reported?" },
      { text: "Which states or LGAs did the partner operate in during this period?" },
      { text: "Are there variances between planned and actual activities, and are they explained?" },
      { text: "Does the financial expenditure align with the activities reported?" },
      { text: "What innovations or success stories were highlighted?" },
      { text: "Did the partner flag any risks or compliance concerns?" },
      { text: "Were any milestones missed, and what is the recovery plan?" },
    ],
  },
];
