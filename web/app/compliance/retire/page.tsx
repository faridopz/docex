"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  Plus,
  Receipt,
  Trash2,
  Wallet,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { retireTravel } from "@/lib/api";
import type {
  ComplianceCheckResult,
  Reconciliation,
  RuleResult,
} from "@/types";

/**
 * Travel Retirement — retire an advance from itemised receipts.
 *
 * Deliberately OCR-free: the traveller types each receipt's amount (or drops a
 * digital PDF receipt we read for free) and attaches photos as proof. DOCex
 * reconciles the total against the advance deterministically and instantly —
 * no waiting on a model, no misread amounts. Reconciliation math lives in the
 * backend (receipts.py); this page just collects lines and shows the result.
 */

const CATEGORIES = ["lodging", "meals", "transport", "other"] as const;

type Row = { amount: string; category: string; date: string; vendor: string };

const emptyRow = (): Row => ({ amount: "", category: "meals", date: "", vendor: "" });

type Phase = "idle" | "loading" | "done" | "error";

export default function RetirePage() {
  const [requester, setRequester] = useState("");
  const [advanceRef, setAdvanceRef] = useState("");
  const [tripStart, setTripStart] = useState("");
  const [tripEnd, setTripEnd] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<ComplianceCheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enteredTotal = rows.reduce((sum, r) => sum + (parseFloat(r.amount) || 0), 0);
  const canSubmit =
    requester.trim().length > 0 &&
    (rows.some((r) => r.amount.trim()) || files.length > 0) &&
    phase !== "loading";

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setPhase("loading");
    setError(null);
    try {
      const receipts = rows
        .filter((r) => r.amount.trim() || r.vendor.trim())
        .map((r) => ({
          amount: r.amount.trim() ? parseFloat(r.amount) : null,
          category: r.category || undefined,
          date: r.date || undefined,
          vendor: r.vendor.trim() || undefined,
        }));
      const res = await retireTravel({
        requesterName: requester.trim(),
        advanceReference: advanceRef.trim() || undefined,
        tripStart: tripStart || undefined,
        tripEnd: tripEnd || undefined,
        receipts,
        files,
      });
      setResult(res);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reconcile the retirement.");
      setPhase("error");
    }
  }

  return (
    <AppShell active="submit">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Link
          href="/compliance"
          className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 transition hover:text-gray-800"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Compliance
        </Link>

        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Wallet className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              Retire a travel advance
            </h1>
            <p className="text-sm text-gray-500">
              Enter your receipts (or drop digital ones) — DOCex reconciles them
              against your advance instantly.
            </p>
          </div>
        </div>

        {result && result.reconciliation ? (
          <ResultView result={result} onReset={() => { setResult(null); setPhase("idle"); }} />
        ) : (
          <div className="space-y-6">
            {/* Who + advance */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Your name">
                <input
                  value={requester}
                  onChange={(e) => setRequester(e.target.value)}
                  placeholder="e.g. Ada Obi"
                  className={inputCls}
                />
              </Field>
              <Field label="Advance reference (optional)" hint="Leave blank if paid out of pocket">
                <input
                  value={advanceRef}
                  onChange={(e) => setAdvanceRef(e.target.value)}
                  placeholder="e.g. pay-9f3a21b8"
                  className={inputCls}
                />
              </Field>
              <Field label="Trip start (optional)">
                <input type="date" value={tripStart} onChange={(e) => setTripStart(e.target.value)} className={inputCls} />
              </Field>
              <Field label="Trip end (optional)">
                <input type="date" value={tripEnd} onChange={(e) => setTripEnd(e.target.value)} className={inputCls} />
              </Field>
            </div>

            {/* Receipt lines */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-semibold text-gray-900">Receipts</label>
                <span className="text-xs text-gray-400">
                  Entered total: <span className="font-medium text-gray-600">{enteredTotal.toLocaleString()}</span>
                </span>
              </div>
              <div className="space-y-2">
                {rows.map((r, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 bg-white p-2">
                    <input
                      value={r.amount}
                      onChange={(e) => updateRow(i, { amount: e.target.value.replace(/[^0-9.]/g, "") })}
                      inputMode="decimal"
                      placeholder="Amount"
                      className="w-28 rounded-md border border-gray-200 px-2.5 py-1.5 text-sm focus:border-blue-600 focus:outline-none"
                    />
                    <select
                      value={r.category}
                      onChange={(e) => updateRow(i, { category: e.target.value })}
                      className="rounded-md border border-gray-200 px-2 py-1.5 text-sm capitalize focus:border-blue-600 focus:outline-none"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c} className="capitalize">{c}</option>
                      ))}
                    </select>
                    <input
                      value={r.vendor}
                      onChange={(e) => updateRow(i, { vendor: e.target.value })}
                      placeholder="Vendor"
                      className="min-w-0 flex-1 rounded-md border border-gray-200 px-2.5 py-1.5 text-sm focus:border-blue-600 focus:outline-none"
                    />
                    <input
                      type="date"
                      value={r.date}
                      onChange={(e) => updateRow(i, { date: e.target.value })}
                      className="rounded-md border border-gray-200 px-2 py-1.5 text-sm text-gray-600 focus:border-blue-600 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs))}
                      className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-50 hover:text-red-600"
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setRows((rs) => [...rs, emptyRow()])}
                className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:border-brand-400 hover:text-brand-600"
              >
                <Plus className="h-4 w-4" />
                Add receipt
              </button>
            </div>

            {/* Evidence / digital receipts */}
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-900">
                Attach receipt photos or PDFs
              </label>
              <p className="text-xs text-gray-500">
                Photos ride along as proof. Digital PDF receipts are read
                automatically — no need to type those amounts.
              </p>
              <DropZone files={files} onFilesChange={setFiles} />
            </div>

            {phase === "error" && error && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
            )}

            <div className="flex justify-end border-t border-gray-100 pt-5">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {phase === "loading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Receipt className="h-4 w-4" />}
                Reconcile & retire
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

/* ─── Result ──────────────────────────────────────────────────────────────── */

const DIRECTION_COPY: Record<Reconciliation["direction"], { label: string; tone: string }> = {
  recover: { label: "Unspent balance to return", tone: "text-amber-700 bg-amber-50 border-amber-200" },
  reimburse: { label: "Reimburse the traveller", tone: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  settled: { label: "Fully settled", tone: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  out_of_pocket: { label: "Reimburse (paid out of pocket)", tone: "text-emerald-700 bg-emerald-50 border-emerald-200" },
};

function ResultView({ result, onReset }: { result: ComplianceCheckResult; onReset: () => void }) {
  const rec = result.reconciliation!;
  const dir = DIRECTION_COPY[rec.direction];
  const money = (n: number | null) => (n === null ? "—" : n.toLocaleString(undefined, { minimumFractionDigits: 2 }));

  return (
    <div className="space-y-5">
      <div className={`rounded-xl border p-5 ${dir.tone}`}>
        <p className="text-xs font-semibold uppercase tracking-wide opacity-70">{dir.label}</p>
        <p className="mt-1 text-2xl font-bold">
          {rec.balance !== null ? money(Math.abs(rec.balance)) : money(rec.total_spent)}
        </p>
        <p className="mt-1 text-sm opacity-90">{rec.summary}</p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Advance" value={money(rec.advance_amount)} />
        <Stat label="Spent" value={money(rec.total_spent)} />
        <Stat label="Receipts" value={`${rec.readable_count}/${rec.receipt_count} read`} />
      </div>

      {rec.flags.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-semibold text-gray-900">Needs attention</p>
          <div className="space-y-2">
            {rec.flags.map((f: RuleResult, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 text-sm ${
                  f.verdict === "block"
                    ? "border-red-200 bg-red-50 text-red-800"
                    : f.verdict === "flag"
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-gray-200 bg-gray-50 text-gray-700"
                }`}
              >
                <span className="font-medium uppercase text-xs mr-2">{f.verdict.replace("_", " ")}</span>
                {f.reasoning}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between border-t border-gray-100 pt-5">
        <button
          type="button"
          onClick={onReset}
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
        >
          Retire another
        </button>
        <Link
          href="/compliance/checks"
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700"
        >
          View in pipeline
        </Link>
      </div>
    </div>
  );
}

/* ─── Small presentational helpers ──────────────────────────────────────── */

const inputCls =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-semibold text-gray-900">{label}</label>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-gray-900">{value}</p>
    </div>
  );
}
