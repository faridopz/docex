"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Loader2, Plus, Send, Trash2, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PolicyCheckList } from "@/components/erp/PolicyChecks";
import {
  createRequisition,
  getWorkflow,
  newIdempotencyKey,
} from "@/lib/requisitionApi";
import { getClientConfig, hasFeature } from "@/lib/orgConfig";
import { humanise, money } from "@/lib/requisitionFormat";
import type { BudgetLine, Payee, PaymentType, Requisition, RequisitionWorkflow } from "@/types/requisition";

/** One payee row as the form edits it — amount stays a raw string (so a
 * comma-typed "20,000" isn't fought while typing) and is only parsed at the
 * boundary, same treatment as the single-vendor amount field below. */
type PayeeRow = Omit<Payee, "amount"> & { amount: string };

const EMPTY_ROW: PayeeRow = {
  name: "", account_number: "", bank_name: "", amount: "",
  purpose: "", tin: "", phone_or_email: "", payee_type: "beneficiary",
};

const PAYEE_TYPES: Payee["payee_type"][] = ["beneficiary", "staff", "vendor"];

/** One budget-line row as the form edits it — quantity/frequency/unit cost
 * stay raw strings for the same reason the amount field does: a partially
 * typed number shouldn't fight the input or silently become 0. The line
 * total shown here is a client-side preview only; the server always
 * recomputes the real one from these three values (DETERMINISTIC-FIRST —
 * nothing typed as a total is ever trusted). */
type BudgetLineRow = Omit<BudgetLine, "quantity" | "frequency" | "unit_cost" | "line_total"> & {
  quantity: string;
  frequency: string;
  unit_cost: string;
};

const EMPTY_BUDGET_ROW: BudgetLineRow = {
  description: "", unit: "", budget_line: "", quantity: "1", frequency: "1", unit_cost: "",
};

const PAYMENT_TYPES: { value: PaymentType; label: string }[] = [
  { value: "full", label: "Full payment" },
  { value: "advance", label: "Advance payment" },
  { value: "balance", label: "Balance payment" },
];

/** Strip thousands separators the way the single-amount field already does,
 * so pasted or typed "1,500,000" parses instead of silently failing. */
function parseMoney(raw: string): number {
  const cleaned = raw.replace(/,/g, "").trim();
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : 0;
}

/** Parse rows pasted from a spreadsheet (tab-separated) or a comma-separated
 * list — the two shapes someone copying a payee list will actually have.
 * Column order matches the row editor: name, account, bank, amount, purpose,
 * phone/email, TIN, type. Missing trailing columns are fine; a line with
 * nothing in it is dropped rather than becoming a blank row. */
function parseBulkPayees(text: string): PayeeRow[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const cells = (line.includes("\t") ? line.split("\t") : line.split(",")).map((c) =>
        c.trim(),
      );
      const [name = "", account_number = "", bank_name = "", amount = "", purpose = "",
        phone_or_email = "", tin = "", typeRaw = ""] = cells;
      const payee_type = (PAYEE_TYPES as string[]).includes(typeRaw.toLowerCase())
        ? (typeRaw.toLowerCase() as Payee["payee_type"])
        : "beneficiary";
      return { name, account_number, bank_name, amount, purpose, phone_or_email, tin, payee_type };
    })
    .filter((row) => row.name !== "" || row.amount !== "");
}

/**
 * Raise a payment requisition.
 *
 * The point of this screen is that policy checks run the moment it is
 * submitted, so the submitter sees the problem while they still have the
 * invoice open — not three days later when an approver bounces it back. The
 * org's actual ceiling, categories and required documents are read from the
 * configured workflow and shown as guidance before anything is typed.
 *
 * Batch mode (multiple payees in one requisition — a stipend list, a
 * beneficiary payout run) only appears when the org has switched on
 * `multi_payee_requisitions`; the backend refuses a payee list from an org
 * that hasn't, so hiding the toggle for everyone else isn't just tidiness,
 * it matches what would actually be accepted.
 *
 * The idempotency key is minted once per attempt and held in a ref: if the
 * connection drops and the user presses submit again, the server replays the
 * first requisition rather than raising a duplicate.
 */
export default function NewRequisitionPage() {
  const [workflow, setWorkflow] = useState<RequisitionWorkflow | null>(null);
  const [multiPayeeEnabled, setMultiPayeeEnabled] = useState(false);

  const [mode, setMode] = useState<"single" | "batch">("single");

  const [vendorName, setVendorName] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [projectCode, setProjectCode] = useState("");
  const [grantCode, setGrantCode] = useState("");
  const [vendorAccount, setVendorAccount] = useState("");
  const [vendorBankName, setVendorBankName] = useState("");
  const [vendorTin, setVendorTin] = useState("");
  const [vendorPhoneOrEmail, setVendorPhoneOrEmail] = useState("");
  const [paymentType, setPaymentType] = useState<PaymentType>("full");
  const [description, setDescription] = useState("");
  const [documents, setDocuments] = useState<string[]>([]);

  const [payeeRows, setPayeeRows] = useState<PayeeRow[]>([{ ...EMPTY_ROW }]);
  const [bulkPaste, setBulkPaste] = useState("");

  const [budgetLines, setBudgetLines] = useState<BudgetLineRow[]>([]);

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
      try {
        const cfg = await getClientConfig();
        if (!cancelled) setMultiPayeeEnabled(hasFeature(cfg, "multi_payee_requisitions"));
      } catch {
        /* Fails closed — the toggle just stays hidden, matching what the
           server would refuse anyway. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const currency = workflow?.currency ?? "NGN";
  // Nigerian naira amounts are near-universally typed with thousands commas
  // ("1,500,000") — Number() on that raw string is NaN, which silently left
  // the submit button disabled with no obvious reason. That is exactly what
  // NEEM hit during the pilot handoff: they filled in a request and nothing
  // happened. Strip thousands separators and stray whitespace before parsing.
  const cleanedAmount = amount.replace(/,/g, "").trim();
  const parsedAmount = Number(cleanedAmount);
  const amountValid = cleanedAmount !== "" && Number.isFinite(parsedAmount) && parsedAmount > 0;

  // ─── batch (multi-payee) math ─────────────────────────────────────────────

  /** A row counts once it has a name and a positive amount — matches exactly
   *  what the backend's PAYEES_VALID check requires, so nothing that would
   *  pass client-side fails at submit for a reason the submitter never saw
   *  coming. */
  const validPayeeRows = useMemo(
    () => payeeRows.filter((r) => r.name.trim() !== "" && parseMoney(r.amount) > 0),
    [payeeRows],
  );
  const payeeTotal = useMemo(
    () => validPayeeRows.reduce((sum, r) => sum + parseMoney(r.amount), 0),
    [validPayeeRows],
  );
  const maxPayees = workflow?.max_payees ?? 100;
  const overPayeeCap = validPayeeRows.length > maxPayees;

  const effectiveAmount = mode === "batch" ? payeeTotal : parsedAmount;
  const effectiveAmountValid = mode === "batch" ? validPayeeRows.length > 0 && !overPayeeCap : amountValid;

  /** Warn about the ceiling before submitting — the server enforces it, but
   *  there is no reason to make someone submit to find out. */
  const overCeiling = useMemo(() => {
    if (!workflow?.max_amount || !effectiveAmountValid) return false;
    return effectiveAmount > workflow.max_amount;
  }, [workflow?.max_amount, effectiveAmount, effectiveAmountValid]);

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
    if (!workflow?.steps?.length || !effectiveAmountValid) return [];
    return workflow.steps
      .filter((s) => effectiveAmount >= (s.min_amount ?? 0))
      .map((s) => s.label || s.key);
  }, [workflow?.steps, effectiveAmount, effectiveAmountValid]);

  const canSubmit = vendorName.trim() !== "" && effectiveAmountValid && !submitting;

  function toggleDocument(doc: string) {
    setDocuments((prev) => (prev.includes(doc) ? prev.filter((d) => d !== doc) : [...prev, doc]));
  }

  function patchPayeeRow(i: number, patch: Partial<PayeeRow>) {
    setPayeeRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function removePayeeRow(i: number) {
    setPayeeRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i)));
  }

  function addPayeeRow() {
    setPayeeRows((prev) => [...prev, { ...EMPTY_ROW }]);
  }

  function patchBudgetRow(i: number, patch: Partial<BudgetLineRow>) {
    setBudgetLines((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function removeBudgetRow(i: number) {
    setBudgetLines((prev) => prev.filter((_, idx) => idx !== i));
  }

  function addBudgetRow() {
    setBudgetLines((prev) => [...prev, { ...EMPTY_BUDGET_ROW }]);
  }

  function addFromPaste() {
    const parsed = parseBulkPayees(bulkPaste);
    if (!parsed.length) return;
    setPayeeRows((prev) => {
      // The form starts with one blank row so it's never empty on screen —
      // pasting real rows should replace that placeholder, not sit next to it.
      const base = prev.length === 1 && prev[0].name === "" && prev[0].amount === "" ? [] : prev;
      return [...base, ...parsed];
    });
    setBulkPaste("");
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
          amount: effectiveAmount,
          category: category.trim(),
          project_code: projectCode.trim(),
          grant_code: grantCode.trim() || undefined,
          vendor_account: mode === "batch" ? "" : vendorAccount.trim(),
          vendor_bank_name: mode === "batch" ? "" : vendorBankName.trim(),
          vendor_tin: mode === "batch" ? "" : vendorTin.trim(),
          vendor_phone_or_email: mode === "batch" ? "" : vendorPhoneOrEmail.trim(),
          payment_type: paymentType,
          budget_lines: budgetLines
            .filter((r) => r.description.trim() !== "")
            .map((r) => ({
              description: r.description.trim(),
              unit: r.unit.trim(),
              budget_line: r.budget_line.trim(),
              quantity: parseMoney(r.quantity) || 1,
              frequency: parseMoney(r.frequency) || 1,
              unit_cost: parseMoney(r.unit_cost),
              line_total: 0, // server-computed — this value is ignored
            })),
          description: description.trim(),
          documents,
          payees:
            mode === "batch"
              ? validPayeeRows.map((r) => ({ ...r, amount: parseMoney(r.amount) }))
              : undefined,
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
    setVendorBankName("");
    setVendorTin("");
    setVendorPhoneOrEmail("");
    setPaymentType("full");
    setDescription("");
    setDocuments([]);
    setPayeeRows([{ ...EMPTY_ROW }]);
    setBulkPaste("");
    setBudgetLines([]);
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
              {money(result.amount, result.currency)}{" "}
              {result.payees.length
                ? `across ${result.payees.length} ${result.payees.length === 1 ? "payee" : "payees"} — "${result.vendor_name}"`
                : `to ${result.vendor_name}`}
              {result.current_step ? ` — now with ${humanise(result.current_step)}` : ""}
            </p>
          </div>

          {result.payees.length > 0 ? (
            <section className="rounded-lg border border-gray-200 bg-white">
              <div className="border-b border-gray-100 px-4 py-2.5">
                <h2 className="text-sm font-semibold text-gray-900">Payees</h2>
              </div>
              <ul className="max-h-64 divide-y divide-gray-50 overflow-y-auto">
                {result.payees.map((p, i) => (
                  <li key={i} className="flex items-center gap-3 px-4 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate text-gray-900">{p.name}</span>
                    <span className="text-xs text-gray-400">{humanise(p.payee_type)}</span>
                    <span className="font-medium text-gray-700">{money(p.amount, result.currency)}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

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

        {multiPayeeEnabled ? (
          <div className="mt-4 inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
            <button
              type="button"
              onClick={() => setMode("single")}
              className={
                mode === "single"
                  ? "rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-gray-900 shadow-sm"
                  : "rounded-md px-3 py-1.5 text-sm font-medium text-gray-500 hover:text-gray-700"
              }
            >
              One payee
            </button>
            <button
              type="button"
              onClick={() => setMode("batch")}
              className={
                mode === "batch"
                  ? "inline-flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-gray-900 shadow-sm"
                  : "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-gray-500 hover:text-gray-700"
              }
            >
              <Users className="h-3.5 w-3.5" /> Many payees
            </button>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="mt-6 space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field
              label={mode === "batch" ? "What is this batch called" : "Who is being paid"}
              hint={mode === "batch" ? "e.g. \"August 2026 workshop stipends\" — the title for this whole payout run." : undefined}
              required
            >
              <input
                value={vendorName}
                onChange={(e) => setVendorName(e.target.value)}
                placeholder={mode === "batch" ? "Batch title" : "Vendor or payee name"}
                className={inputClass}
                required
              />
            </Field>

            {mode === "single" ? (
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
            ) : (
              <Field label={`Total (${currency})`} hint="Computed from the payee rows below.">
                <div className={`${inputClass} flex items-center bg-gray-50 font-semibold text-gray-900`}>
                  {money(payeeTotal, currency)}
                </div>
                {overCeiling && workflow?.max_amount ? (
                  <p className="mt-1 text-xs text-amber-700">
                    Above the {money(workflow.max_amount, currency)} ceiling — this will need an
                    override from someone who holds that authority.
                  </p>
                ) : null}
              </Field>
            )}

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

            <Field label="Payment type" hint="Full, or an advance/balance split">
              <select
                value={paymentType}
                onChange={(e) => setPaymentType(e.target.value as PaymentType)}
                className={inputClass}
              >
                {PAYMENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>

            {mode === "single" ? (
              <>
                <Field label="Vendor bank account">
                  <input
                    value={vendorAccount}
                    onChange={(e) => setVendorAccount(e.target.value)}
                    placeholder="Optional"
                    className={inputClass}
                  />
                </Field>
                <Field label="Bank name">
                  <input
                    value={vendorBankName}
                    onChange={(e) => setVendorBankName(e.target.value)}
                    placeholder="Optional"
                    className={inputClass}
                  />
                </Field>
                <Field label="Tax Identification Number (TIN)">
                  <input
                    value={vendorTin}
                    onChange={(e) => setVendorTin(e.target.value)}
                    placeholder="Optional"
                    className={inputClass}
                  />
                </Field>
                <Field label="Phone / email">
                  <input
                    value={vendorPhoneOrEmail}
                    onChange={(e) => setVendorPhoneOrEmail(e.target.value)}
                    placeholder="Optional"
                    className={inputClass}
                  />
                </Field>
              </>
            ) : null}
          </div>

          {mode === "batch" ? (
            <PayeeEditor
              rows={payeeRows}
              currency={currency}
              maxPayees={maxPayees}
              validCount={validPayeeRows.length}
              overCap={overPayeeCap}
              bulkPaste={bulkPaste}
              onBulkPasteChange={setBulkPaste}
              onAddFromPaste={addFromPaste}
              onPatchRow={patchPayeeRow}
              onRemoveRow={removePayeeRow}
              onAddRow={addPayeeRow}
            />
          ) : null}

          <BudgetLineEditor
            rows={budgetLines}
            currency={currency}
            onPatchRow={patchBudgetRow}
            onRemoveRow={removeBudgetRow}
            onAddRow={addBudgetRow}
          />

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

const payeeInputClass =
  "w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 shadow-sm transition placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";

/**
 * The payee table for a batch requisition — a stipend list or beneficiary
 * payout run. Two ways in: type rows one at a time, or paste a list copied
 * from a spreadsheet (tab-separated columns, one payee per line) so raising
 * a 100-payee requisition isn't 100 rounds of manual typing.
 *
 * A row only counts toward the total/payee-count once it has a name and a
 * positive amount — this mirrors the backend's PAYEES_VALID check exactly,
 * so a half-filled trailing row doesn't silently inflate what's about to be
 * submitted.
 */
function PayeeEditor({
  rows,
  currency,
  maxPayees,
  validCount,
  overCap,
  bulkPaste,
  onBulkPasteChange,
  onAddFromPaste,
  onPatchRow,
  onRemoveRow,
  onAddRow,
}: {
  rows: PayeeRow[];
  currency: string;
  maxPayees: number;
  validCount: number;
  overCap: boolean;
  bulkPaste: string;
  onBulkPasteChange: (v: string) => void;
  onAddFromPaste: () => void;
  onPatchRow: (i: number, patch: Partial<PayeeRow>) => void;
  onRemoveRow: (i: number) => void;
  onAddRow: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">
          Payees
          <span className="ml-0.5 text-red-500">*</span>
        </span>
        <span className={overCap ? "text-xs font-semibold text-red-600" : "text-xs text-gray-500"}>
          {validCount} / {maxPayees} payees
        </span>
      </div>

      {overCap ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          This organisation limits a single requisition to {maxPayees} payees. Remove some rows or
          split this into more than one requisition.
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="bg-gray-50 text-[11px] uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-2 py-2 font-medium">#</th>
              <th className="px-2 py-2 font-medium">Name *</th>
              <th className="px-2 py-2 font-medium">Account no.</th>
              <th className="px-2 py-2 font-medium">Bank</th>
              <th className="px-2 py-2 font-medium">Type</th>
              <th className="px-2 py-2 font-medium">Amount ({currency}) *</th>
              <th className="px-2 py-2 font-medium">Purpose</th>
              <th className="px-2 py-2 font-medium">Phone / email</th>
              <th className="px-2 py-2 font-medium">TIN</th>
              <th className="px-2 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row, i) => {
              const rowValid = row.name.trim() !== "" && parseMoney(row.amount) > 0;
              return (
                <tr key={i} className={rowValid ? undefined : "bg-amber-50/40"}>
                  <td className="px-2 py-1.5 text-gray-400">{i + 1}</td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.name}
                      onChange={(e) => onPatchRow(i, { name: e.target.value })}
                      placeholder="Full name"
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.account_number}
                      onChange={(e) => onPatchRow(i, { account_number: e.target.value })}
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.bank_name}
                      onChange={(e) => onPatchRow(i, { bank_name: e.target.value })}
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <select
                      value={row.payee_type}
                      onChange={(e) =>
                        onPatchRow(i, { payee_type: e.target.value as Payee["payee_type"] })
                      }
                      className={payeeInputClass}
                    >
                      {PAYEE_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {humanise(t)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.amount}
                      onChange={(e) => onPatchRow(i, { amount: e.target.value })}
                      inputMode="decimal"
                      placeholder="0.00"
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.purpose}
                      onChange={(e) => onPatchRow(i, { purpose: e.target.value })}
                      placeholder="If it differs from above"
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.phone_or_email}
                      onChange={(e) => onPatchRow(i, { phone_or_email: e.target.value })}
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      value={row.tin}
                      onChange={(e) => onPatchRow(i, { tin: e.target.value })}
                      className={payeeInputClass}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      onClick={() => onRemoveRow(i)}
                      disabled={rows.length <= 1}
                      className="text-gray-300 transition hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-30"
                      title="Remove row"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button
        type="button"
        onClick={onAddRow}
        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50"
      >
        <Plus className="h-3.5 w-3.5" /> Add payee
      </button>

      <details className="rounded-lg border border-gray-200 bg-gray-50/60 p-3">
        <summary className="cursor-pointer text-xs font-medium text-gray-600">
          Paste a list instead (from Excel or a CSV)
        </summary>
        <p className="mt-2 text-xs text-gray-500">
          One payee per line, columns in this order: name, account number, bank, amount, purpose,
          phone or email, TIN, type (staff / vendor / beneficiary). Copy straight out of a
          spreadsheet — tab-separated rows paste in as-is.
        </p>
        <textarea
          value={bulkPaste}
          onChange={(e) => onBulkPasteChange(e.target.value)}
          rows={4}
          placeholder={"Aisha Bello\t0123456789\tGTBank\t20000\tStipend\n..."}
          className="mt-2 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-xs text-gray-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          type="button"
          onClick={onAddFromPaste}
          disabled={!bulkPaste.trim()}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-gray-800 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-gray-900 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Add pasted rows
        </button>
      </details>
    </div>
  );
}

/**
 * Optional expense breakdown — mirrors the item table on NEEM's own memo
 * ("Description/Item, Unit of Measurement, Budget Line, Quantity,
 * Frequency, Unit Cost, Total Amount"). Empty by default: a requisition
 * with no rows behaves exactly as before this existed. The total shown per
 * row is a live preview only — the server always recomputes it from
 * quantity * frequency * unit cost and ignores anything sent as a total.
 */
function BudgetLineEditor({
  rows,
  currency,
  onPatchRow,
  onRemoveRow,
  onAddRow,
}: {
  rows: BudgetLineRow[];
  currency: string;
  onPatchRow: (i: number, patch: Partial<BudgetLineRow>) => void;
  onRemoveRow: (i: number) => void;
  onAddRow: () => void;
}) {
  const grandTotal = rows.reduce(
    (sum, r) => sum + parseMoney(r.quantity) * parseMoney(r.frequency) * parseMoney(r.unit_cost),
    0,
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">
          Budget breakdown
          <span className="ml-1.5 font-normal text-gray-400">(optional)</span>
        </span>
        {rows.length ? (
          <span className="text-xs text-gray-500">
            Preview total {money(grandTotal, currency)} — recalculated on submit
          </span>
        ) : null}
      </div>

      {rows.length ? (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full min-w-[820px] text-left text-xs">
            <thead className="bg-gray-50 text-[11px] uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-2 py-2 font-medium">#</th>
                <th className="px-2 py-2 font-medium">Description / item</th>
                <th className="px-2 py-2 font-medium">Unit</th>
                <th className="px-2 py-2 font-medium">Budget line</th>
                <th className="px-2 py-2 font-medium">Qty</th>
                <th className="px-2 py-2 font-medium">Freq.</th>
                <th className="px-2 py-2 font-medium">Unit cost ({currency})</th>
                <th className="px-2 py-2 font-medium">Total</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((row, i) => {
                const lineTotal =
                  parseMoney(row.quantity) * parseMoney(row.frequency) * parseMoney(row.unit_cost);
                return (
                  <tr key={i}>
                    <td className="px-2 py-1.5 text-gray-400">{i + 1}</td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.description}
                        onChange={(e) => onPatchRow(i, { description: e.target.value })}
                        placeholder="e.g. Flip chart"
                        className={payeeInputClass}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.unit}
                        onChange={(e) => onPatchRow(i, { unit: e.target.value })}
                        placeholder="Pieces"
                        className={payeeInputClass}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.budget_line}
                        onChange={(e) => onPatchRow(i, { budget_line: e.target.value })}
                        className={payeeInputClass}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.quantity}
                        onChange={(e) => onPatchRow(i, { quantity: e.target.value })}
                        inputMode="decimal"
                        className={`${payeeInputClass} w-16`}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.frequency}
                        onChange={(e) => onPatchRow(i, { frequency: e.target.value })}
                        inputMode="decimal"
                        className={`${payeeInputClass} w-16`}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <input
                        value={row.unit_cost}
                        onChange={(e) => onPatchRow(i, { unit_cost: e.target.value })}
                        inputMode="decimal"
                        placeholder="0.00"
                        className={payeeInputClass}
                      />
                    </td>
                    <td className="px-2 py-1.5 whitespace-nowrap font-medium text-gray-700">
                      {money(lineTotal, currency)}
                    </td>
                    <td className="px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => onRemoveRow(i)}
                        className="text-gray-300 transition hover:text-red-500"
                        title="Remove row"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <button
        type="button"
        onClick={onAddRow}
        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50"
      >
        <Plus className="h-3.5 w-3.5" /> Add line item
      </button>
    </div>
  );
}
