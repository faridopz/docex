/**
 * Types mirroring api/reconciliation_routes.py serialisers.
 *
 * Unions rather than `string` for the codes and severities, deliberately: on a
 * screen where colour tells a finance officer whether money is unexplained, a
 * mistyped comparison should be a build error, not a payment quietly rendered
 * green.
 */

export type MatchMethod = "reference" | "exact" | "vendor" | "manual";

export type ExceptionCode =
  | "NOT_IN_BANK"
  | "NOT_IN_SYSTEM"
  | "AMOUNT_MISMATCH"
  | "AMBIGUOUS"
  | "DUPLICATE_BANK_LINE";

export type Severity = "high" | "medium" | "low";

export interface ColumnMap {
  date: string;
  description: string;
  reference: string;
  debit: string;
  credit: string;
  amount: string;
  date_format: string;
  /** True when the importer worked the layout out rather than being told it. */
  detected: boolean;
}

export interface BankLineRow {
  id: string;
  row: number;
  date: string;
  description: string;
  reference: string;
  amount: number;
  direction: "in" | "out";
}

export interface ReconMatch {
  transaction_id: string;
  transaction_ref: string;
  bank_line_id: string;
  bank_row: number;
  method: MatchMethod;
  amount: number;
  paid_at: string;
  bank_date: string;
  day_gap: number;
  vendor_name: string;
  matched_by: string;
  reason: string;
}

export interface ReconException {
  code: ExceptionCode;
  severity: Severity;
  amount: number;
  date: string;
  description: string;
  transaction_id: string;
  transaction_ref: string;
  bank_line_id: string;
  bank_row: number;
  candidates: string[];
  note: string;
}

/** What GET /reconciliation returns per run, and what summary() produces. */
export interface ReconRunSummary {
  run_id: string;
  period: string;
  statement: string;
  statement_sha256: string;
  payments_in_system: number;
  debits_in_bank: number;
  matched: number;
  matched_value: number;
  total_paid_in_system: number;
  total_debits_in_bank: number;
  variance: number;
  exceptions_by_code: Partial<Record<ExceptionCode, number>>;
  unresolved_high: number;
  reconciled: boolean;
  locked: boolean;
  closed_by: string;
}

export interface ReconRun extends ReconRunSummary {
  period_start: string;
  period_end: string;
  column_map: ColumnMap;
  date_window_days: number;
  matches: ReconMatch[];
  /** Already sorted highest severity first by the server. */
  exceptions: ReconException[];
  bank_lines: BankLineRow[];
  created_at: string;
  created_by: string;
  closed_at: string;
}

export interface StatementPreview {
  column_map: ColumnMap;
  auto_detected: boolean;
  lines_total: number;
  debits: number;
  credits: number;
  debit_value: number;
  first_date: string;
  last_date: string;
  sample: BankLineRow[];
  confirm: string;
}
