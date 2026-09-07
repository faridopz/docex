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

export interface TimeEntry {
  date: string;
  hours: number;
  project_code: string;
  activity: string;
  /** Derived: an hour with a real project code is chargeable. */
  chargeable: boolean;
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
  submitted_by: string;
  submitted_at: string;
  approved_by: string;
  approved_at: string;
  returned_reason: string;
  updated_at: string;
}

export interface Timesheet extends TimesheetSummary {
  entries: TimeEntry[];
  hours_by_project: Record<string, number>;
  /** The number that reaches payroll: % of chargeable effort per project. */
  effort_allocation: Record<string, number>;
  issues: EffortIssue[];
  blocking: number;
}

export interface TimesheetPolicy {
  org_id: string;
  standard_hours_per_period: number;
  tolerance_hours: number;
  require_activity_description: boolean;
  updated_at: string | null;
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
}
