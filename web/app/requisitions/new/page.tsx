"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Loader2, Send } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PolicyCheckList } from "@/components/erp/PolicyChecks";
import {
  createRequisition,
  getWorkflow,
  newIdempotencyKey,
} from "@/lib/requisitionApi";
import { humanise, money } from "@/lib/requisitionFormat";
import type { Requisition, RequisitionWorkflow } from "@/types/requisition";

/**
 * Raise a payment requisition.
 *
 * The point of this screen is that policy checks run the moment it is
 * submitted, so the submitter sees the problem while they still have the
 * invoice open — not three days later when an approver bounces it back. The
 * org's actual ceiling, categories and required documents are read from the
 * configured workflow and shown as guidance before anything is typed.
 *
 * The idempotency key is minted once per attempt and held in a ref: if the
 * connection drops and the user presses submit again, the server replays the
 * first requisition rather than raising a duplicate.
 */
export default function NewRequisitionPage() {
  const [workflow, setWorkflow] = useState<RequisitionWorkflow | null>(null);

  const [vendorName, setVendorName] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [projectCode, setProjectCode] = useState("");
  const [grantCode, setGrantCode] = useState("");
  const [vendorAccount, setVendorAccount] = useState("");
  const [description, setDescription] = useState("");
  const [documents, setDocuments] = useState<string[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Requisition | null>(null);

  // One key per logical submission. Cleared only after a success, so every
  // retry of the same attempt carries the same key.
  const idemKey = useRef<string>(newIdempotencyKey());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const wf = await getWorkflow();
        if (!cancelled) setWorkflow(wf);
      } catch {
        /* Guidance is a nicety; the form still works without it. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const currency = workflow?.currency ?? "NGN";
  const parsedAmount = Number(amount);
  const amountValid = amount.trim() !== "" && Number.isFinite(parsedAmount) && parsedAmount > 0;

  /** Warn about the ceiling before submitting — the server enforces it, but
   *  there is no reason to make someone submit to find out. */
  const overCeiling = useMemo(() => {
    if (!workflow?.max_amount || !amountValid) return false;
    return parsedAmount > workflow.max_amount;
  }, [workflow?.max_amount, parsedAmount, amountValid]);

  /** Which approvers this amount will actually pass through.
   *
   *  A step only engages at or above its min_amount, so the chain changes as
   *  the amount is typed. Showing it before submitting answers the question
   *  every submitter actually has — "who has to sign this, and how long will
   *  it take?" — instead of leaving them to find out when it lands somewhere
   *  unexpected. The workflow is already loaded for the ceiling warning, so
   *  this costs nothing extra.
   */
  const approvalRoute = useMemo(() => {
    if (!workflow?.steps?.length || !amountValid) return [];
    return workflow.steps
      .filter((s) => parsedAmount >= (s.min_amount ?? 0))
      .map((s) => s.label || s.key);
  }, [workflow?.steps, parsedAmount, amountValid]);

  const canSubmit = vendorName.trim() !== "" && amountValid && !submitting;

  function toggleDocument(doc: string) {
    setDocuments((prev) => (prev.includes(doc) ? prev.filter((d) => d !== doc) : [...prev, doc]));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);
    try {
      const req = await createRequisition(
        {
          vendor_name: vendorName.trim(),
          amount: parsedAmount,
          category: category.trim(),
          project_code: projectCode.trim(),
          grant_code: grantCode.trim() || undefined,
          vendor_account: vendorAccount.trim(),
          description: description.trim(),
          documents,
          currency,
        },
        idemKey.current,
      );
      setResult(req);
      // Fresh key so the next requisition on this screen is a new write.
      idemKey.current = newIdempotencyKey();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not raise this requisition.");
    } finally {
      setSubmitting(false);
    }
  }

  function startAnother() {
    setResult(null);
    setError(null);
    setVendorName("");
    setAmount("");
    setCategory("");
    setProjectCode("");
    setGrantCode("");
    setVendorAccount("");
    setDescription("");
    setDocuments([]);
  }

  // ─── result view ──────────────────────────────────────────────────────────

  if (result) {
    const blocking = result.checks.filter((c) => c.result === "fail" && !c.overridden);
    const warnings = result.checks.filter((c) => c.result === "warning");

    return (
      <AppShell>
        <div className="mx-auto max-w-3xl space-y-6">
          <div>
            <p className="text-sm text-gray-500">Requisition raised</p>
            <h1 className="mt-0.5 text-2xl font-bold tracking-tight text-gray-900">{result.ref}</h1>
            <p className="mt-1 text-sm text-gray-600">
              {money(result.amount, result.currency)} to {result.vendor_name}
              {result.current_step ? ` — now with ${humanise(result.current_step)}` : ""}
            </p>
          </div>

          {blocking.length > 0 ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-semibold text-red-900">
                {blocking.length} {blocking.length === 1 ? "check blocks" : "checks block"} payment
              </p>
              <p className="mt-1 text-sm text-red-800">
                Fix these now if you can. An approver can only release them by recording a written
                reason against their own name, and every release is read at audit.
              </p>
            </div>
          ) : warnings.length > 0 ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">
                Cleared with {warnings.length} {warnings.length === 1 ? "warning" : "warnings"}
              </p>
              <p className="mt-1 text-sm text-amber-800">
                Nothing blocks payment. The warnings travel with the requisition so an approver sees
                the same picture you do.
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-sm font-semibold text-emerald-900">Every policy check passed</p>
              <p className="mt-1 text-sm text-emerald-800">
                This requisition needs no exception to be paid.
              </p>
            </div>
          )}

          <section>
            <h2 className="mb-2 text-sm font-semibold text-gray-900">Policy checks</h2>
            <PolicyCheckList checks={result.checks} />
          </section>

          <div className="flex flex-wrap gap-3 border-t border-gray-200 pt-5">
            <Link
              href={`/requisitions/${encodeURIComponent(result.id)}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700"
            >
              Open {result.ref}
              <ArrowRight className="h-4 w-4" />
            </Link>
            <button
              type="button"
              onClick={startAnother}
              className="rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
            >
              Raise another
            </button>
            <Link
              href="/requisitions"
              className="rounded-lg px-3.5 py-2 text-sm font-medium text-gray-600 transition hover:text-gray-900"
            >
              Back to requisitions
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  // ─── form ─────────────────────────────────────────────────────────────────

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">New payment requisition</h1>
          <p className="mt-1 text-sm text-gray-600">
            Policy checks run as soon as you submit, so you see any problem before an approver does.
          </p>
        </div>

        {workflow ? <PolicySummary workflow={workflow} /> : null}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Who is being paid" required>
              <input
                value={vendorName}
                onChange={(e) => setVendorName(e.target.value)}
                placeholder="Vendor or payee name"
                className={inputClass}
                required
              />
            </Field>

            <Field label={`Amount (${currency})`} required>
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="decimal"
                placeholder="0.00"
                className={inputClass}
                required
              />
              {amount.trim() !== "" && !amountValid ? (
                <p className="mt-1 text-xs text-red-600">Enter an amount greater than zero.</p>
              ) : overCeiling && workflow?.max_amount ? (
                <p className="mt-1 text-xs text-amber-700">
                  Above the {money(workflow.max_amount, currency)} ceiling — this will need an
                  override from someone who holds that authority.
                </p>
              ) : null}
            </Field>

            <Field label="Category">
              {workflow?.allowed_categories.length ? (
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className={inputClass}
                >
                  <option value="">Select a category…</option>
                  {workflow.allowed_categories.map((c) => (
                    <option key={c} value={c}>
                      {humanise(c)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="e.g. training, supplies, travel"
                  className={inputClass}
                />
              )}
            </Field>

            <Field label="Project / cost centre">
              <input
                value={projectCode}
                onChange={(e) => setProjectCode(e.target.value)}
                placeholder="e.g. P-101"
                className={inputClass}
              />
            </Field>

            <Field label="Grant code" hint="Which grant this is charged to">
              <input
                value={grantCode}
                onChange={(e) => setGrantCode(e.target.value)}
                placeholder="Optional"
                className={inputClass}
              />
            </Field>

            <Field label="Vendor bank account">
              <input
                value={vendorAccount}
                onChange={(e) => setVendorAccount(e.target.value)}
                placeholder="Optional"
                className={inputClass}
              />
            </Field>
          </div>

          <Field label="What this is for">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="One or two lines an approver can act on without calling you."
              className={inputClass}
            />
          </Field>

          {workflow?.required_documents.length ? (
            <Field
              label="Supporting documents attached"
              hint="Your policy requires these. Anything unticked comes back as a blocking check."
            >
              <div className="flex flex-wrap gap-2">
                {workflow.required_documents.map((doc) => {
                  const on = documents.includes(doc);
                  return (
                    <button
                      key={doc}
                      type="button"
                      onClick={() => toggleDocument(doc)}
                      className={
                        on
                          ? "rounded-full border border-brand-600 bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700"
                          : "rounded-full border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-50"
                      }
                      aria-pressed={on}
                    >
                      {humanise(doc)}
                    </button>
                  );
                })}
              </div>
            </Field>
          ) : null}

          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          ) : null}

          {/* Where this is about to go. The chain depends on the amount, so it
              updates as you type — the submitter learns that ₦300,000 needs the
              ED before they submit, not after it lands there. */}
          {approvalRoute.length ? (
            <div className="rounded-lg border border-gray-200 bg-gray-50/80 p-3.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                This will go to
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {approvalRoute.map((label, i) => (
                  <span key={label} className="flex items-center gap-1.5">
                    {i > 0 ? <span className="text-gray-400">→</span> : null}
                    <span className="rounded-md bg-white px-2 py-1 text-sm font-medium text-gray-800 ring-1 ring-gray-200">
                      {label}
                    </span>
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-500">
                {approvalRoute.length === 1
                  ? "One approval at this amount."
                  : `${approvalRoute.length} approvals at this amount.`}
              </p>
            </div>
          ) : null}

          <div className="flex items-center gap-3 border-t border-gray-200 pt-5">
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {submitting ? "Running policy checks…" : "Submit requisition"}
            </button>
            <Link
              href="/requisitions"
              className="text-sm font-medium text-gray-600 transition hover:text-gray-900"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </AppShell>
  );
}

// ─── small pieces ───────────────────────────────────────────────────────────

const inputClass =
  "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm transition placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-gray-700">
        {label}
        {required ? <span className="ml-0.5 text-red-500">*</span> : null}
      </span>
      {hint ? <span className="mb-1.5 block text-xs text-gray-500">{hint}</span> : null}
      {children}
    </label>
  );
}

/** The org's own spend policy, stated up front rather than discovered later. */
function PolicySummary({ workflow }: { workflow: RequisitionWorkflow }) {
  const bits: string[] = [];
  if (workflow.max_amount) {
    bits.push(`Ceiling ${money(workflow.max_amount, workflow.currency)}`);
  }
  if (workflow.required_documents.length) {
    bits.push(`${workflow.required_documents.length} required documents`);
  }
  if (workflow.duplicate_window_days) {
    bits.push(`Duplicate window ${workflow.duplicate_window_days} days`);
  }
  const steps = workflow.steps.length;
  if (steps) bits.push(`${steps} approval ${steps === 1 ? "step" : "steps"}`);

  if (!bits.length) return null;

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Your spend policy</p>
      <p className="mt-1 text-sm text-gray-700">{bits.join(" · ")}</p>
    </div>
  );
}
