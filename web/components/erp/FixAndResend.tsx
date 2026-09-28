"use client";

/**
 * Fix and send again — shown to the person who raised a request when it has
 * been returned to them (or is still a draft).
 *
 * Found in the 28 Sep live walkthrough: a returned request could only be
 * "resubmitted" unchanged, so an approver's "add the project code" or "the
 * amount is wrong" could not be acted on, and the reason itself sat far down
 * the page. This puts the reason first, the fields beneath it, and one button
 * that saves the corrections and sends the request back into the chain.
 * Every change is written to the audit log as old → new by the server.
 */
import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { humanise, money } from "@/lib/requisitionFormat";
import {
  resubmitRequisition,
  submitRequisition,
  updateRequisitionDraft,
} from "@/lib/requisitionApi";
import type { Requisition } from "@/types/requisition";

type Field =
  | "vendor_name" | "amount" | "category" | "project_code" | "grant_code"
  | "vendor_bank_name" | "vendor_account" | "vendor_tin" | "vendor_phone_or_email" | "description";

const input =
  "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";

export function FixAndResend({
  req,
  categories,
  returnedBy,
  onDone,
}: {
  req: Requisition;
  categories: string[];
  /** The decision that sent it back: who, when, and their note. */
  returnedBy: { name: string; at: string; note: string } | null;
  onDone: (r: Requisition) => void;
}) {
  const isDraft = req.status === "draft";
  const batch = req.payees.length > 0;
  const initial: Record<Field, string> = {
    vendor_name: req.vendor_name || "",
    amount: String(req.amount ?? ""),
    category: req.category || "",
    project_code: req.project_code || "",
    grant_code: req.grant_code || "",
    vendor_bank_name: req.vendor_bank_name || "",
    vendor_account: req.vendor_account || "",
    vendor_tin: req.vendor_tin || "",
    vendor_phone_or_email: req.vendor_phone_or_email || "",
    description: req.description || "",
  };
  const [vals, setVals] = useState(initial);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (k: Field) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setVals((v) => ({ ...v, [k]: e.target.value }));

  const changed = (Object.keys(vals) as Field[]).filter(
    (k) => !(batch && (k === "vendor_name" || k === "amount" || k.startsWith("vendor_"))) && vals[k].trim() !== initial[k].trim(),
  );

  async function go() {
    setBusy(true);
    setError(null);
    try {
      let current = req;
      if (changed.length) {
        const fields: Record<string, string> = {};
        for (const k of changed) fields[k] = k === "amount" ? vals[k].replace(/,/g, "") : vals[k].trim();
        current = await updateRequisitionDraft(req.id, fields);
      }
      current = isDraft ? await submitRequisition(req.id) : await resubmitRequisition(req.id, note.trim());
      onDone(current);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save.");
    } finally {
      setBusy(false);
    }
  }

  const categoryOptions = Array.from(new Set([...(categories || []), vals.category].filter(Boolean)));

  return (
    <section className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      {returnedBy ? (
        <div className="mb-4">
          <p className="text-sm font-semibold text-amber-900">
            Returned to you by {returnedBy.name}
            {returnedBy.at ? <span className="font-normal text-amber-800"> · {returnedBy.at}</span> : null}
          </p>
          {returnedBy.note ? (
            <p className="mt-1 rounded-md bg-white/70 px-3 py-2 text-sm text-amber-950">“{returnedBy.note}”</p>
          ) : null}
          <p className="mt-2 text-xs text-amber-800">
            Correct anything below, attach any missing documents further down, then send it again. It goes back to the
            first approver, and every change is recorded.
          </p>
        </div>
      ) : (
        <p className="mb-4 text-sm font-semibold text-amber-900">
          This is a draft — nobody has seen it yet. Check the details, then send it for approval.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {!batch ? (
          <>
            <Labelled label="Who is being paid">
              <input value={vals.vendor_name} onChange={set("vendor_name")} className={input} />
            </Labelled>
            <Labelled label={`Amount (${req.currency})`}>
              <input value={vals.amount} onChange={set("amount")} inputMode="decimal" className={input} />
            </Labelled>
          </>
        ) : (
          <p className="text-xs text-amber-900 sm:col-span-2">
            This request pays {req.payees.length} people ({money(req.amount, req.currency)}). To change the list of
            payees, decline it and raise a new one.
          </p>
        )}
        <Labelled label="Category">
          <select value={vals.category} onChange={set("category")} className={input}>
            <option value="">—</option>
            {categoryOptions.map((c) => (
              <option key={c} value={c}>
                {humanise(c)}
              </option>
            ))}
          </select>
        </Labelled>
        <Labelled label="Project / cost centre">
          <input value={vals.project_code} onChange={set("project_code")} className={input} />
        </Labelled>
        <Labelled label="Grant code">
          <input value={vals.grant_code} onChange={set("grant_code")} className={input} />
        </Labelled>
        {!batch ? (
          <>
            <Labelled label="Bank name">
              <input value={vals.vendor_bank_name} onChange={set("vendor_bank_name")} className={input} />
            </Labelled>
            <Labelled label="Account number">
              <input value={vals.vendor_account} onChange={set("vendor_account")} inputMode="numeric" className={input} />
            </Labelled>
            <Labelled label="Tax ID (TIN)">
              <input value={vals.vendor_tin} onChange={set("vendor_tin")} className={input} />
            </Labelled>
          </>
        ) : null}
        <Labelled label="What this is for" wide>
          <textarea value={vals.description} onChange={set("description")} rows={2} className={input} />
        </Labelled>
        {!isDraft ? (
          <Labelled label="What did you fix? (the approver sees this)" wide>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={input}
              placeholder="e.g. Corrected the amount and attached the invoice" />
          </Labelled>
        ) : null}
      </div>

      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={go}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {isDraft ? "Send for approval" : changed.length ? "Save changes and send again" : "Send again"}
        </button>
        <span className="text-xs text-amber-800">
          {changed.length ? `${changed.length} change${changed.length === 1 ? "" : "s"} will be saved` : "No changes yet"}
        </span>
      </div>
    </section>
  );
}

function Labelled({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`block ${wide ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-xs font-medium text-amber-950">{label}</span>
      {children}
    </label>
  );
}
