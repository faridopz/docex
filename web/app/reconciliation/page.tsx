"use client";

import { listBankAccounts, type BankAccount } from "@/lib/bankAccountsApi";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  Lock,
  ShieldAlert,
  Upload,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { getAccountMap } from "@/lib/accountingApi";
import { getDocumentPermissions, triggerBlobDownload } from "@/lib/requisitionApi";
import { AppShell } from "@/components/AppShell";
import {
  closePeriod,
  DATE_FORMAT_CHOICES,
  downloadQuickBooksFile,
  downloadReconReport,
  explainException,
  explainMany,
  getRun,
  isAmbiguousDateError,
  listRuns,
  previewStatement,
  reviewPeriod,
  runReconciliation,
  type QuickBooksFileKind,
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

  // Which account this statement is for. Only asked when the organisation
  // has more than one — a statement is compared with the payments from ITS
  // account, never with every project's payments.
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  useEffect(() => {
    listBankAccounts()
      .then((a) => setAccounts(a.filter((x) => x.active)))
      .catch(() => setAccounts([]));
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
        accountId: accountId || undefined,
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

  async function onExplainMany(bankLineIds: string[], reason: string) {
    if (!run || !reason.trim() || bankLineIds.length === 0) return;
    setBusy("explain-many");
    setError(null);
    try {
      setRun(await explainMany(run.run_id, bankLineIds, reason));
    } catch (e) {
      fail(e, "Could not record that explanation.");
    } finally {
      setBusy(null);
    }
  }

  async function onReview() {
    if (!run) return;
    setBusy("review");
    setError(null);
    try {
      setRun(await reviewPeriod(run.run_id));
      await refreshRuns();
    } catch (e) {
      fail(e, "Could not sign this month off.");
    } finally {
      setBusy(null);
    }
  }

  // A previous month opens in full: it is where the second person signs off,
  // and where Finance comes back for the QuickBooks files and the report.
  async function onOpenRun(runId: string) {
    setBusy("open");
    setError(null);
    try {
      setRun(await getRun(runId));
      window.scrollTo({ top: 0 });
    } catch (e) {
      fail(e, "Could not open that month.");
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
            accounts={accounts}
            accountId={accountId}
            setAccountId={setAccountId}
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
            onExplainMany={onExplainMany}
            onReview={onReview}
            onStartOver={reset}
            run={run}
          />
        )}

        {!run && !loading && runs.length > 0 && <PastRuns onOpen={onOpenRun} runs={runs} />}
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
  accounts: BankAccount[];
  accountId: string;
  setAccountId: (id: string) => void;
}) {
  const {
    accounts,
    accountId,
    setAccountId,
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

        {accounts.length > 1 ? (
          <label className="text-sm">
            <span className="mb-1 block font-medium text-gray-700">Account</span>
            <select
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
              onChange={(e) => setAccountId(e.target.value)}
              value={accountId}
            >
              <option value="">Read it from the statement…</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

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
  onExplainMany: (bankLineIds: string[], reason: string) => void;
  onReview: () => void;
  onStartOver: () => void;
  run: ReconRun;
}) {
  const { busy, onClose, onExplain, onExplainMany, onReview, onStartOver, run } = props;
  const { user } = useAuth();
  const [forceReason, setForceReason] = useState("");
  const [forcing, setForcing] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [groupReason, setGroupReason] = useState("");
  const [showCharges, setShowCharges] = useState(false);

  const charges = run.exceptions.filter((e) => e.code === "BANK_CHARGE");
  const unexplained = run.exceptions.filter((e) => e.severity === "high");
  const other = run.exceptions.filter((e) => e.severity !== "high" && e.code !== "BANK_CHARGE");
  // Only bank lines can be explained together; a gap is fixed by the bank.
  const selectable = unexplained.filter((e) => e.bank_line_id && e.code !== "STATEMENT_GAP");
  const complete = run.statement_complete;
  const iClosed = !!user?.email && user.email.toLowerCase() === (run.closed_by || "").toLowerCase();

  function toggle(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

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
            {run.account_label ? (
              <p className="mt-0.5 text-xs font-medium text-gray-500">{run.account_label}</p>
            ) : null}
            <p className="mt-1 text-sm text-gray-700">
              {run.matched} of {run.payments_in_system} approved payment
              {run.payments_in_system === 1 ? "" : "s"} confirmed by the bank.
              {complete === true
                ? " The statement is complete — every running balance agrees."
                : complete === false
                  ? " The statement is incomplete — rows are missing or altered."
                  : " (No balance column, so completeness could not be checked.)"}
            </p>
            {run.opening_balance != null && run.closing_balance != null ? (
              <p className="mt-1 text-xs text-gray-600">
                Opening {money(run.opening_balance)} + in {money(run.money_in_total ?? 0)} − out{" "}
                {money(run.total_debits_in_bank)} = closing {money(run.closing_balance)}
              </p>
            ) : null}
            {run.locked && (
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-gray-600">
                <Lock className="h-3.5 w-3.5" />
                Closed by {run.closed_by} on {shortDate(run.closed_at)}
                {run.reviewed_by
                  ? ` · signed off by ${run.reviewed_by} on ${shortDate(run.reviewed_at || "")}`
                  : " · awaiting a second person's sign-off"}
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Approved & confirmed" value={money(run.matched_value)} sub={`${run.matched} payment${run.matched === 1 ? "" : "s"}`} tone="good" />
        <Tile label="Bank charges" value={money(run.bank_charges_total ?? 0)} sub={`${run.bank_charges_count ?? 0} item${run.bank_charges_count === 1 ? "" : "s"}`} />
        <Tile label="Money in" value={money(run.money_in_total ?? 0)} sub={`${run.money_in_count ?? 0} receipt${run.money_in_count === 1 ? "" : "s"}`} />
        <Tile label="Needs attention" value={String(unexplained.length)} sub={unexplained.length ? "explain before closing" : "nothing outstanding"} tone={unexplained.length ? "bad" : "good"} />
      </div>

      {unexplained.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Needs an explanation
          </h3>
          {!run.locked && selectable.length > 1 ? (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
              <p className="text-xs text-gray-600">
                Several with the same answer? Tick them, give one reason, record once.
              </p>
              {selected.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <input
                    className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
                    onChange={(e) => setGroupReason(e.target.value)}
                    placeholder={`One reason for the ${selected.length} ticked item${selected.length === 1 ? "" : "s"}`}
                    value={groupReason}
                  />
                  <button
                    className="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
                    disabled={!groupReason.trim() || busy !== null}
                    onClick={() => {
                      onExplainMany(selected, groupReason);
                      setSelected([]);
                      setGroupReason("");
                    }}
                    type="button"
                  >
                    {busy === "explain-many" ? <Loader2 className="h-4 w-4 animate-spin" /> : `Explain ${selected.length}`}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
          {unexplained.map((exc) => (
            <div className="flex items-start gap-2" key={`${exc.code}-${exc.bank_line_id || exc.transaction_id}-${exc.bank_row}`}>
              {!run.locked && selectable.length > 1 && selectable.includes(exc) ? (
                <input
                  aria-label="Select to explain together"
                  checked={selected.includes(exc.bank_line_id)}
                  className="mt-5 h-4 w-4"
                  onChange={() => toggle(exc.bank_line_id)}
                  type="checkbox"
                />
              ) : null}
              <div className="min-w-0 flex-1">
                <ExceptionCard busy={busy} exc={exc} locked={run.locked} onExplain={onExplain} />
              </div>
            </div>
          ))}
        </section>
      )}

      {charges.length > 0 && (
        <section className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <button
            className="flex w-full items-center justify-between text-left"
            onClick={() => setShowCharges((v) => !v)}
            type="button"
          >
            <span className="text-sm font-medium text-gray-900">
              Bank charges · {charges.length} item{charges.length === 1 ? "" : "s"} · {money(run.bank_charges_total ?? 0)}
            </span>
            <span className="text-xs text-gray-500">{showCharges ? "Hide" : "Show"}</span>
          </button>
          <p className="mt-1 text-xs text-gray-500">
            The bank&rsquo;s own fees (SMS alerts, stamp duty, transfer fees, VAT on fees), recognised
            from the narration. Posted to QuickBooks as one entry.
          </p>
          {showCharges ? (
            <ul className="mt-3 divide-y divide-gray-100 text-sm">
              {charges.map((c) => (
                <li className="flex justify-between py-1.5" key={c.bank_line_id}>
                  <span className="text-gray-700">{shortDate(c.date)} · {c.description}</span>
                  <span className="text-gray-900">{money(c.amount)}</span>
                </li>
              ))}
            </ul>
          ) : null}
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

      {run.locked && !run.reviewed_by ? (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 className="font-medium text-gray-900">Second signature</h3>
          <p className="mt-1 text-sm text-gray-600">
            A month checked only by the person who prepared it isn&rsquo;t checked. Someone other than{" "}
            {run.closed_by} signs it off.
          </p>
          {iClosed ? (
            <p className="mt-3 text-sm text-gray-500">You closed this month, so someone else in Finance signs it off.</p>
          ) : (
            <button
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              disabled={busy !== null}
              onClick={onReview}
              type="button"
            >
              {busy === "review" ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" />}
              I&rsquo;ve checked it — sign off {periodLabel(run.period)}
            </button>
          )}
        </div>
      ) : null}

      <QuickBooksCard run={run} />

      <p className="text-xs text-gray-400">
        Statement: {run.statement} · fingerprint {run.statement_sha256} · reconciled
        by {run.created_by || "—"}
      </p>
    </div>
  );
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: "good" | "bad" }) {
  const box = tone === "bad" ? "border-red-200 bg-red-50" : tone === "good" ? "border-emerald-200 bg-emerald-50" : "border-gray-200 bg-white";
  return (
    <div className={`rounded-xl border p-3 ${box}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-base font-semibold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500">{sub}</p>
    </div>
  );
}

const EDITION_LABEL: Record<string, string> = {
  online_international: "QuickBooks Online (international)",
  online_us: "QuickBooks Online (US)",
  desktop: "QuickBooks Desktop",
};

/**
 * Send to QuickBooks. Everything comes FROM this reconciliation, so only money
 * the bank confirmed — and DOCex approved — reaches the books.
 *
 * Every edition: the bank file, uploaded in place of the raw statement, each
 * line already saying what it is. The US edition and Desktop can also import
 * journals, which post each payment to its account and project class outright
 * (closed months only). Intuit: the international edition cannot import
 * journals, so it is not offered there.
 */
function QuickBooksCard({ run }: { run: ReconRun }) {
  const [edition, setEdition] = useState("online_international");
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDocumentPermissions()
      .then((p) => setAllowed(!!p.handles_money))
      .catch(() => setAllowed(false));
    getAccountMap()
      .then((m) => setEdition((m as { edition?: string }).edition || "online_international"))
      .catch(() => undefined);
  }, []);

  if (!allowed) return null;

  async function get(kind: QuickBooksFileKind | "report") {
    setBusy(kind);
    setError(null);
    try {
      const { blob, filename } = kind === "report"
        ? await downloadReconReport(run.run_id)
        : await downloadQuickBooksFile(run.run_id, kind);
      triggerBlobDownload(blob, filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not download that file.");
    } finally {
      setBusy("");
    }
  }

  const journalKind: QuickBooksFileKind | null =
    edition === "online_us" ? "journal" : edition === "desktop" ? "iif" : null;
  const btn = "inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40";

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="font-medium text-gray-900">Send to QuickBooks</h3>
      <p className="mt-1 text-sm text-gray-600">
        For {EDITION_LABEL[edition] || edition}. Upload the bank file in QuickBooks under{" "}
        <span className="font-medium">Banking → Upload from file</span>, instead of the raw statement —
        every line already says who was paid, the request, the account and the project.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className={btn} disabled={!!busy} onClick={() => get("bank")} type="button">
          {busy === "bank" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          Bank file for QuickBooks
        </button>
        {journalKind ? (
          <button
            className={btn}
            disabled={!!busy || !run.locked}
            onClick={() => get(journalKind)}
            title={run.locked ? "" : "Close the month first"}
            type="button"
          >
            {busy === journalKind ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            {journalKind === "iif" ? "Journal file (IIF)" : "Journal file"}
          </button>
        ) : null}
        <button className={btn} disabled={!!busy} onClick={() => get("report")} type="button">
          {busy === "report" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
          Reconciliation report (Excel)
        </button>
      </div>
      {journalKind && !run.locked ? (
        <p className="mt-2 text-xs text-gray-500">
          The journal file is available once the month is closed, so the books only receive confirmed payments.
        </p>
      ) : null}
      <p className="mt-2 text-xs text-gray-500">
        Tip: in QuickBooks, one bank rule per expense account (&ldquo;Description contains · Venue costs ·&rdquo;)
        files these lines by itself every month.
      </p>
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
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

function PastRuns({ runs, onOpen }: { runs: ReconRunSummary[]; onOpen: (runId: string) => void }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Previous months
      </h3>
      <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
        {runs.map((r) => (
          <button
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-gray-50"
            key={r.run_id}
            onClick={() => onOpen(r.run_id)}
            type="button"
          >
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
              {r.locked ? (
                <span className="text-xs text-gray-500">{r.reviewed_by ? "Signed off" : "Awaiting sign-off"}</span>
              ) : null}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
