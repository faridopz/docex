"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  Loader2,
  Lock,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  closePeriod,
  DATE_FORMAT_CHOICES,
  explainException,
  isAmbiguousDateError,
  listRuns,
  previewStatement,
  runReconciliation,
} from "@/lib/reconciliationApi";
import {
  EXCEPTION_ACTION,
  EXCEPTION_TITLE,
  METHOD_LABEL,
  METHOD_STYLE,
  money,
  periodLabel,
  recentPeriods,
  SEVERITY_LABEL,
  SEVERITY_STYLE,
  shortDate,
} from "@/lib/reconciliationFormat";
import type {
  ReconException,
  ReconRun,
  ReconRunSummary,
  StatementPreview,
} from "@/types/reconciliation";

/**
 * Month-end bank reconciliation.
 *
 * The screen is built around one question — is there money we cannot explain —
 * and it refuses to let that question be answered by accident.
 *
 * Three deliberate choices:
 *
 *  1. PREVIEW BEFORE COMMITTING. Bank layouts differ, and a wrong column
 *     mapping produces a reconciliation that looks clean over the wrong
 *     pairing. The upload step shows how the importer read the file, with
 *     sample rows, before anything is stored against the period.
 *
 *  2. EXCEPTIONS FIRST, MATCHES SECOND. The matched list is the boring half.
 *     Unexplained money leads, and the screen says what to do about each item
 *     rather than only naming it.
 *
 *  3. CLOSING IS A DECISION. The Close button is disabled while anything is
 *     unexplained. Forcing it takes a written reason, and the reason is stored
 *     against the closer's name — the server enforces this too, the UI just
 *     refuses to send a request it knows will be rejected.
 */
export default function ReconciliationPage() {
  const [runs, setRuns] = useState<ReconRunSummary[]>([]);
  const [run, setRun] = useState<ReconRun | null>(null);
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [period, setPeriod] = useState<string>(recentPeriods(1)[0]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Set only when the importer could not prove the date format from the file.
  const [needsDateFormat, setNeedsDateFormat] = useState(false);
  const [dateFormat, setDateFormat] = useState("");
  const [loading, setLoading] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  const periods = useMemo(() => recentPeriods(6), []);

  const refreshRuns = useCallback(async () => {
    try {
      setRuns(await listRuns());
    } catch {
      /* the list is context, not the point of the screen */
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refreshRuns();
      setLoading(false);
    })();
  }, [refreshRuns]);

  function fail(e: unknown, fallback: string) {
    setError(e instanceof Error ? e.message : fallback);
  }

  const doPreview = useCallback(async (f: File, fmt: string) => {
    setBusy("preview");
    setError(null);
    try {
      setPreview(await previewStatement(f, { dateFormat: fmt || undefined }));
      setNeedsDateFormat(false);
    } catch (e) {
      // Not a failure the user caused, and not a dead end: the file simply
      // does not settle day-first vs month-first. Ask, then retry.
      if (isAmbiguousDateError(e) && !fmt) {
        setNeedsDateFormat(true);
        setPreview(null);
      } else {
        fail(e, "Could not read that statement.");
      }
    } finally {
      setBusy(null);
    }
  }, []);

  async function onPickFile(f: File | null) {
    setFile(f);
    setPreview(null);
    setError(null);
    setNeedsDateFormat(false);
    setDateFormat("");
    if (!f) return;
    await doPreview(f, "");
  }

  async function onChooseDateFormat(fmt: string) {
    setDateFormat(fmt);
    if (file) await doPreview(file, fmt);
  }

  async function onReconcile() {
    if (!file) return;
    setBusy("reconcile");
    setError(null);
    try {
      setRun(await runReconciliation(period, file, {
        dateFormat: dateFormat || undefined,
      }));
      await refreshRuns();
    } catch (e) {
      fail(e, "Could not reconcile.");
    } finally {
      setBusy(null);
    }
  }

  async function onExplain(exc: ReconException, reason: string) {
    if (!run || !reason.trim()) return;
    setBusy(`explain-${exc.bank_line_id || exc.transaction_id}`);
    setError(null);
    try {
      setRun(await explainException(run.run_id, reason, {
        bankLineId: exc.bank_line_id || undefined,
        transactionId: exc.bank_line_id ? undefined : exc.transaction_id || undefined,
      }));
    } catch (e) {
      fail(e, "Could not record that explanation.");
    } finally {
      setBusy(null);
    }
  }

  async function onClose(forceReason = "") {
    if (!run) return;
    setBusy("close");
    setError(null);
    try {
      setRun(await closePeriod(run.run_id, forceReason));
      await refreshRuns();
    } catch (e) {
      fail(e, "Could not close the period.");
    } finally {
      setBusy(null);
    }
  }

  function reset() {
    setRun(null);
    setPreview(null);
    setFile(null);
    setError(null);
    setNeedsDateFormat(false);
    setDateFormat("");
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-6 pb-16">
        <header>
          <h1 className="text-xl font-semibold text-gray-900">Bank reconciliation</h1>
          <p className="mt-1 text-sm text-gray-600">
            Check what the bank says left the account against what DOCex says was
            paid — in both directions.
          </p>
        </header>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error}
          </div>
        )}

        {!run && (
          <UploadCard
            busy={busy}
            dateFormat={dateFormat}
            file={file}
            fileInput={fileInput}
            needsDateFormat={needsDateFormat}
            onChooseDateFormat={onChooseDateFormat}
            onPickFile={onPickFile}
            onReconcile={onReconcile}
            period={period}
            periods={periods}
            preview={preview}
            setPeriod={setPeriod}
          />
        )}

        {run && (
          <RunView
            busy={busy}
            onClose={onClose}
            onExplain={onExplain}
            onStartOver={reset}
            run={run}
          />
        )}

        {!run && !loading && runs.length > 0 && <PastRuns runs={runs} />}
      </div>
    </AppShell>
  );
}

/* ── upload + preview ─────────────────────────────────────────────────────── */

function UploadCard(props: {
  busy: string | null;
  dateFormat: string;
  file: File | null;
  fileInput: React.RefObject<HTMLInputElement>;
  needsDateFormat: boolean;
  onChooseDateFormat: (fmt: string) => void;
  onPickFile: (f: File | null) => void;
  onReconcile: () => void;
  period: string;
  periods: string[];
  preview: StatementPreview | null;
  setPeriod: (p: string) => void;
}) {
  const {
    busy,
    dateFormat,
    file,
    fileInput,
    needsDateFormat,
    onChooseDateFormat,
    onPickFile,
    onReconcile,
    period,
    periods,
    preview,
    setPeriod,
  } = props;

  return (
    <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm">
          <span className="mb-1 block font-medium text-gray-700">Month</span>
          <select
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            onChange={(e) => setPeriod(e.target.value)}
            value={period}
          >
            {periods.map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="mb-1 block font-medium text-gray-700">Bank statement</span>
          <input
            accept=".csv,.xlsx,.xlsm,.tsv,.txt"
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-blue-700"
            onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
            ref={fileInput}
            type="file"
          />
        </label>
      </div>

      <p className="text-xs text-gray-500">
        Export one account for one month, as CSV or Excel. Nothing is saved until
        you reconcile.
      </p>

      {busy === "preview" && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Reading the statement…
        </div>
      )}

      {needsDateFormat && (
        <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="text-sm">
              <p className="font-medium text-gray-900">
                Which way round are the dates?
              </p>
              <p className="mt-0.5 text-gray-700">
                Every date in this file could be read either way, so DOCex will
                not guess — reading them wrong would move payments into the
                wrong month. Nigerian banks write the day first.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {DATE_FORMAT_CHOICES.map((c) => (
              <button
                className={`rounded-lg border px-3 py-2 text-left text-sm ${
                  dateFormat === c.value
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-300 bg-white hover:bg-gray-50"
                }`}
                disabled={busy !== null}
                key={c.value}
                onClick={() => onChooseDateFormat(c.value)}
                type="button"
              >
                <span className="block font-medium text-gray-900">{c.label}</span>
                <span className="block text-xs text-gray-500">{c.example}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {preview && (
        <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50/50 p-4">
          <div className="flex items-start gap-2">
            <FileSpreadsheet className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
            <div className="text-sm">
              <p className="font-medium text-gray-900">
                Read {preview.lines_total} rows — {preview.debits} payments out
                totalling {money(preview.debit_value)}, {preview.credits} in.
              </p>
              <p className="text-gray-600">
                {shortDate(preview.first_date)} to {shortDate(preview.last_date)}.{" "}
                {preview.auto_detected
                  ? "Columns were detected automatically."
                  : "Using your saved column mapping."}
              </p>
            </div>
          </div>

          <p className="text-xs text-gray-600">{preview.confirm}</p>

          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-3 py-2">Row</th>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Description</th>
                  <th className="px-3 py-2">Reference</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {preview.sample.map((l) => (
                  <tr key={l.id}>
                    <td className="px-3 py-2 text-gray-400">{l.row}</td>
                    <td className="whitespace-nowrap px-3 py-2">{shortDate(l.date)}</td>
                    <td className="max-w-xs truncate px-3 py-2 text-gray-700">
                      {l.description || "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-500">{l.reference || "—"}</td>
                    <td
                      className={`whitespace-nowrap px-3 py-2 text-right font-medium ${
                        l.direction === "out" ? "text-gray-900" : "text-emerald-700"
                      }`}
                    >
                      {l.direction === "out" ? "−" : "+"}
                      {money(l.amount).replace("₦", "₦ ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            disabled={busy !== null || !file}
            onClick={onReconcile}
            type="button"
          >
            {busy === "reconcile" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Reconcile {periodLabel(period)}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── the result ───────────────────────────────────────────────────────────── */

function RunView(props: {
  busy: string | null;
  onClose: (forceReason?: string) => void;
  onExplain: (exc: ReconException, reason: string) => void;
  onStartOver: () => void;
  run: ReconRun;
}) {
  const { busy, onClose, onExplain, onStartOver, run } = props;
  const [forceReason, setForceReason] = useState("");
  const [forcing, setForcing] = useState(false);

  const unexplained = run.exceptions.filter((e) => e.severity === "high");
  const other = run.exceptions.filter((e) => e.severity !== "high");

  return (
    <div className="space-y-6">
      {/* The verdict, before any detail. */}
      <div
        className={`rounded-xl border p-5 ${
          run.reconciled
            ? "border-emerald-200 bg-emerald-50"
            : "border-red-200 bg-red-50"
        }`}
      >
        <div className="flex items-start gap-3">
          {run.reconciled ? (
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
          )}
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-gray-900">
              {run.reconciled
                ? `${periodLabel(run.period)} reconciles`
                : `${unexplained.length} item${unexplained.length === 1 ? "" : "s"} nobody has explained`}
            </h2>
            <p className="mt-1 text-sm text-gray-700">
              {run.matched} of {run.payments_in_system} payments matched the bank.
              DOCex says {money(run.total_paid_in_system)} went out; the bank says{" "}
              {money(run.total_debits_in_bank)}.{" "}
              {Math.abs(run.variance) < 0.005 ? (
                "The two agree."
              ) : (
                <span className="font-medium">
                  A difference of {money(Math.abs(run.variance))}.
                </span>
              )}
            </p>
            {run.locked && (
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-gray-600">
                <Lock className="h-3.5 w-3.5" />
                Closed by {run.closed_by} on {shortDate(run.closed_at)} — this record
                cannot be edited.
              </p>
            )}
          </div>
          <button
            className="shrink-0 text-sm text-gray-500 underline hover:text-gray-700"
            onClick={onStartOver}
            type="button"
          >
            New reconciliation
          </button>
        </div>
      </div>

      {unexplained.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Needs an explanation
          </h3>
          {unexplained.map((exc) => (
            <ExceptionCard
              busy={busy}
              exc={exc}
              key={`${exc.code}-${exc.bank_line_id || exc.transaction_id}-${exc.bank_row}`}
              locked={run.locked}
              onExplain={onExplain}
            />
          ))}
        </section>
      )}

      {other.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Explained and informational
          </h3>
          {other.map((exc) => (
            <ExceptionCard
              busy={busy}
              exc={exc}
              key={`${exc.code}-${exc.bank_line_id || exc.transaction_id}-${exc.bank_row}`}
              locked={run.locked}
              onExplain={onExplain}
            />
          ))}
        </section>
      )}

      {run.matches.length > 0 && <MatchTable run={run} />}

      {!run.locked && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="font-medium text-gray-900">Close {periodLabel(run.period)}</h3>
          <p className="mt-1 text-sm text-gray-600">
            Once closed, this reconciliation becomes evidence and cannot be
            changed. A correction means importing the statement again as a new
            run.
          </p>

          {unexplained.length === 0 ? (
            <button
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              disabled={busy !== null}
              onClick={() => onClose()}
              type="button"
            >
              {busy === "close" && <Loader2 className="h-4 w-4 animate-spin" />}
              <Lock className="h-4 w-4" />
              Close the month
            </button>
          ) : !forcing ? (
            <div className="mt-3 space-y-2">
              <button
                className="cursor-not-allowed rounded-lg bg-gray-200 px-4 py-2 text-sm font-medium text-gray-500"
                disabled
                type="button"
              >
                Close the month
              </button>
              <p className="text-xs text-gray-500">
                Explain all {unexplained.length} outstanding item
                {unexplained.length === 1 ? "" : "s"} first, or{" "}
                <button
                  className="underline hover:text-gray-700"
                  onClick={() => setForcing(true)}
                  type="button"
                >
                  close anyway with a written reason
                </button>
                .
              </p>
            </div>
          ) : (
            <div className="mt-3 space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="flex items-start gap-2 text-sm text-amber-900">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                Closing over {unexplained.length} unexplained item
                {unexplained.length === 1 ? "" : "s"} is recorded against your name.
              </p>
              <textarea
                className="w-full rounded-lg border border-gray-300 p-2 text-sm"
                onChange={(e) => setForceReason(e.target.value)}
                placeholder="Why is it acceptable to close the month with this outstanding?"
                rows={2}
                value={forceReason}
              />
              <div className="flex gap-2">
                <button
                  className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                  disabled={!forceReason.trim() || busy !== null}
                  onClick={() => onClose(forceReason)}
                  type="button"
                >
                  Close with this reason
                </button>
                <button
                  className="text-sm text-gray-600 underline"
                  onClick={() => setForcing(false)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-gray-400">
        Statement: {run.statement} · fingerprint {run.statement_sha256} · reconciled
        by {run.created_by || "—"}
      </p>
    </div>
  );
}

function ExceptionCard(props: {
  busy: string | null;
  exc: ReconException;
  locked: boolean;
  onExplain: (exc: ReconException, reason: string) => void;
}) {
  const { busy, exc, locked, onExplain } = props;
  const [reason, setReason] = useState("");
  const key = `explain-${exc.bank_line_id || exc.transaction_id}`;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY_STYLE[exc.severity]}`}
            >
              {SEVERITY_LABEL[exc.severity]}
            </span>
            <h4 className="font-medium text-gray-900">{EXCEPTION_TITLE[exc.code]}</h4>
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {money(exc.amount)} · {shortDate(exc.date)}
            {exc.description ? ` · ${exc.description}` : ""}
            {exc.transaction_ref ? ` · ${exc.transaction_ref}` : ""}
            {exc.bank_row ? ` · statement row ${exc.bank_row}` : ""}
          </p>
          <p className="mt-2 text-sm text-gray-700">{exc.note}</p>
          {exc.candidates.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-gray-500">
              {exc.candidates.map((c) => (
                <li key={c}>· {c}</li>
              ))}
            </ul>
          )}
          {exc.severity === "high" && (
            <p className="mt-2 text-xs font-medium text-gray-500">
              {EXCEPTION_ACTION[exc.code]}
            </p>
          )}
        </div>
      </div>

      {exc.severity === "high" && !locked && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
          <input
            className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explain this item — it stays on the record either way"
            value={reason}
          />
          <button
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
            disabled={!reason.trim() || busy !== null}
            onClick={() => onExplain(exc, reason)}
            type="button"
          >
            {busy === key ? <Loader2 className="h-4 w-4 animate-spin" /> : "Record"}
          </button>
        </div>
      )}
    </div>
  );
}

function MatchTable({ run }: { run: ReconRun }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Matched — {run.matches.length} payment{run.matches.length === 1 ? "" : "s"},{" "}
        {money(run.matched_value)}
      </h3>
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2">Payment</th>
              <th className="px-4 py-2">Vendor</th>
              <th className="px-4 py-2 text-right">Amount</th>
              <th className="px-4 py-2">Bank date</th>
              <th className="px-4 py-2">How it matched</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {run.matches.map((m) => (
              <tr key={m.bank_line_id}>
                <td className="px-4 py-2 font-medium text-gray-900">
                  {m.transaction_ref || m.transaction_id}
                </td>
                <td className="max-w-[14rem] truncate px-4 py-2 text-gray-700">
                  {m.vendor_name || "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right">{money(m.amount)}</td>
                <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                  {shortDate(m.bank_date)}
                  {m.day_gap > 0 && (
                    <span className="ml-1 text-xs text-gray-400">
                      (+{m.day_gap}d)
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${METHOD_STYLE[m.method]}`}
                  >
                    {METHOD_LABEL[m.method]}
                  </span>
                  {m.reason && (
                    <span className="ml-2 text-xs text-gray-500">{m.reason}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PastRuns({ runs }: { runs: ReconRunSummary[] }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Previous months
      </h3>
      <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
        {runs.map((r) => (
          <div className="flex items-center justify-between px-4 py-3 text-sm" key={r.run_id}>
            <div>
              <span className="font-medium text-gray-900">{periodLabel(r.period)}</span>
              <span className="ml-2 text-gray-500">
                {r.matched} matched · {money(r.total_debits_in_bank)} out
              </span>
            </div>
            <div className="flex items-center gap-2">
              {r.locked && (
                <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                  <Lock className="h-3 w-3" />
                  Closed
                </span>
              )}
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                  r.reconciled
                    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                    : "bg-red-50 text-red-700 ring-red-200"
                }`}
              >
                {r.reconciled ? "Reconciled" : `${r.unresolved_high} unexplained`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
