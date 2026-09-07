/**
 * Bank reconciliation API client.
 *
 * Thin typed wrappers over apiFetch. Every write is multipart, matching the
 * Form(...) routes on the server; apiFetch leaves FormData's Content-Type
 * alone so the multipart boundary survives.
 */
import { apiFetch } from "@/lib/session";
import type {
  ColumnMap,
  ReconRun,
  ReconRunSummary,
  StatementPreview,
} from "@/types/reconciliation";

function form(fields: Record<string, string | number | undefined | null>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue;
    fd.append(k, String(v));
  }
  return fd;
}

export async function listRuns(period?: string): Promise<ReconRunSummary[]> {
  const qs = period ? `?period=${encodeURIComponent(period)}` : "";
  const r = await apiFetch<{ runs: ReconRunSummary[] }>(`/reconciliation${qs}`);
  return r.runs ?? [];
}

export function getRun(runId: string): Promise<ReconRun> {
  return apiFetch<ReconRun>(`/reconciliation/${encodeURIComponent(runId)}`);
}

/**
 * Read a statement without storing anything.
 *
 * Worth its own call: bank layouts differ, and a wrong column mapping produces
 * a reconciliation that looks clean over the wrong pairing. Preview lets a
 * human confirm the import was read correctly before it is committed against
 * a period.
 */
export function previewStatement(
  file: File,
  opts: { columnMap?: ColumnMap; dateFormat?: string } = {},
): Promise<StatementPreview> {
  const fd = new FormData();
  fd.append("statement", file);
  if (opts.columnMap) fd.append("column_map", JSON.stringify(opts.columnMap));
  if (opts.dateFormat) fd.append("date_format", opts.dateFormat);
  return apiFetch<StatementPreview>("/reconciliation/preview", { method: "POST", body: fd });
}

/**
 * The importer refuses to guess a date column where every value reads both
 * ways — 07/09 is ambiguous, 25/09 is not. Early in a month that is the normal
 * case, not an edge one, so the screen has to recognise it and ask rather than
 * showing the user a dead end.
 */
export function isAmbiguousDateError(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : String(e ?? "");
  return /date_format|day\/month|month\/day/i.test(msg);
}

export const DATE_FORMAT_CHOICES: { value: string; label: string; example: string }[] = [
  { value: "%d/%m/%Y", label: "Day first", example: "07/09/2026 = 7 September" },
  { value: "%m/%d/%Y", label: "Month first", example: "07/09/2026 = 9 July" },
];

export function runReconciliation(
  period: string,
  file: File,
  opts: { columnMap?: ColumnMap; dateFormat?: string; dateWindowDays?: number } = {},
): Promise<ReconRun> {
  const fd = new FormData();
  fd.append("period", period);
  fd.append("statement", file);
  if (opts.columnMap) fd.append("column_map", JSON.stringify(opts.columnMap));
  if (opts.dateFormat) fd.append("date_format", opts.dateFormat);
  if (opts.dateWindowDays != null) fd.append("date_window_days", String(opts.dateWindowDays));
  return apiFetch<ReconRun>("/reconciliation", { method: "POST", body: fd });
}

/** Justify an unmatched item. It is downgraded and kept, never deleted. */
export function explainException(
  runId: string,
  reason: string,
  target: { bankLineId?: string; transactionId?: string },
): Promise<ReconRun> {
  return apiFetch<ReconRun>(`/reconciliation/${encodeURIComponent(runId)}/explain`, {
    method: "POST",
    body: form({
      reason,
      bank_line_id: target.bankLineId,
      transaction_id: target.transactionId,
    }),
  });
}

/** Pair a payment with a bank line the engine would not pair itself. */
export function manualMatch(
  runId: string,
  transactionId: string,
  bankLineId: string,
  reason: string,
): Promise<ReconRun> {
  return apiFetch<ReconRun>(`/reconciliation/${encodeURIComponent(runId)}/match`, {
    method: "POST",
    body: form({ transaction_id: transactionId, bank_line_id: bankLineId, reason }),
  });
}

/**
 * Lock the month. `forceReason` is only needed when unexplained high-severity
 * exceptions remain — the server refuses without it and stores it against the
 * closer's name when given.
 */
export function closePeriod(runId: string, forceReason = ""): Promise<ReconRun> {
  return apiFetch<ReconRun>(`/reconciliation/${encodeURIComponent(runId)}/close`, {
    method: "POST",
    body: form({ force_reason: forceReason }),
  });
}

export async function getColumnMap(): Promise<ColumnMap | null> {
  const r = await apiFetch<{ column_map: ColumnMap | null }>("/reconciliation/columns");
  return r.column_map;
}

export function setColumnMap(cmap: ColumnMap): Promise<ColumnMap> {
  return apiFetch<ColumnMap>("/reconciliation/columns", {
    method: "PUT",
    body: JSON.stringify(cmap),
  });
}
