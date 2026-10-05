/**
 * Types mirroring api/timesheet_routes.py serialisers.
 *
 * Unions rather than `string` for status, so a wrong comparison on a screen
 * that gates payroll is a build error rather than a silently missing sheet.
 */

export type TimesheetStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "returned"
  | "processed";

export type EntryStatus = "pending" | "approved" | "rejected";

export interface EntryCounts {
  pending: number;
  approved: number;
  rejected: number;
}

export interface TimeEntry {
  id: string;
  date: string;
  hours: number;
  project_code: string;
  activity: string;
  /** How much time the line covers: a day, a week (from its Monday or the 1st), or the month. */
  span: "day" | "week" | "month";
  /** Derived: an hour with a real project code is chargeable. */
  chargeable: boolean;
  /** Each entry is reviewed on its own; an approved one can't be changed. */
  status: EntryStatus;
  reject_reason: string;
  reviewed_by: string;
  /** A flag for the supervisor; it does not change pay. */
  overtime: boolean;
}

export interface EffortIssue {
  code: string;
  /** True = cannot be submitted. False = a warning the supervisor should see. */
  blocking: boolean;
  message: string;
}

export interface TimesheetSummary {
  id: string;
  staff_id: string;
  staff_name: string;
  period: string;
  office: string;
  status: TimesheetStatus;
  total_hours: number;
  days: number;
  projects: string[];
  hours_by_project: Record<string, number>;
  /** How this sheet records time; "mixed" only for a sheet that needs fixing. */
  span: "day" | "week" | "month" | "mixed";
  submitted_by: string;
  submitted_at: string;
  approved_by: string;
  approved_at: string;
  returned_reason: string;
  entry_counts: EntryCounts;
  updated_at: string;
}

export interface Timesheet extends TimesheetSummary {
  entries: TimeEntry[];
  /** Code → project title and donor, for showing names rather than codes. */
  project_names: Record<string, { title: string; donor: string }>;
  hours_by_project: Record<string, number>;
  /** The number that reaches payroll: % of chargeable effort per project. */
  effort_allocation: Record<string, number>;
  issues: EffortIssue[];
  blocking: number;
  /** For a submitted sheet: whose signature it waits for. */
  stage?: "" | "supervisor" | "second";
  supervisor_approved_by?: string;
  supervisor_approved_at?: string;
  /** Past the grace period: the employee can no longer change it. */
  locked?: boolean;
  lock_date?: string | null;
  /** A full working day for this month, by the org's own standard. */
  hours_per_day?: number;
}

export interface TimesheetPolicy {
  org_id: string;
  standard_hours_per_period: number;
  tolerance_hours: number;
  require_activity_description: boolean;
  allowed_spans: ("day" | "week" | "month")[];
  /** Days after month-end staff may still change entries; null = no lock. */
  grace_days: number | null;
  /** Department whose approver signs after the supervisor; "" = one signature. */
  second_approval: string;
  /** Who is expected to record time. */
  who_records: "everyone" | "project_staff";
  updated_at: string | null;
}

export interface OutstandingPerson {
  staff_id: string;
  name: string;
  status?: string;
  stage?: string;
}

export interface MyProject {
  project_code: string;
  title: string;
  donor: string;
  planned_percent: number;
}

export interface PeriodSummary {
  period: string;
  timesheets: number;
  by_status: Record<TimesheetStatus, number>;
  hours_by_project: Record<string, number>;
  total_hours: number;
  /** False while any sheet is unapproved — payroll should wait. */
  ready_for_payroll: boolean;
  outstanding_staff: string[];
  /** Expected to record time but no sheet at all for the month. */
  not_started?: OutstandingPerson[];
  /** Started, not sent (draft or returned). */
  not_submitted?: OutstandingPerson[];
  awaiting_approval?: OutstandingPerson[];
  expected?: number;
}

export interface TeamRow {
  staff_id: string;
  name: string;
  department: string;
  timesheet_id: string | null;
  status: TimesheetStatus | "not_started";
  stage: "" | "supervisor" | "second";
  total_hours: number;
  entry_counts: EntryCounts;
}

export interface TeamView {
  period: string;
  rows: TeamRow[];
  counters: { needs_review: number; approved: number; has_rejections: number; not_started: number };
}
