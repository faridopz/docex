"use client";

/**
 * Withholding tax settings.
 *
 * The organisation enters its own schedule here. DOCex ships no rates at all:
 * Nigerian WHT differs by payment type AND by whether the payee is a company
 * or an individual, and it moves with legislation. A default would be a
 * confident wrong deduction on a real invoice — and a wrong deduction is not
 * a display bug, it is money that did not reach a vendor.
 *
 * So the empty state here is deliberate and says so. Nothing is withheld until
 * a finance team enters the schedule their auditor gave them.
 */

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Save, Calculator, AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { listDepartments } from "@/lib/erpApi";
import {
  getWhtPolicy,
  setWhtPolicy,
  previewWht,
  type WHTPolicy,
  type WHTRule,
  type PayeeType,
  type WHTResult,
} from "@/lib/whtApi";

const inputCls =
  "rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand-400";

const PAYEE_TYPES: { value: PayeeType; label: string }[] = [
  { value: "company", label: "Company" },
  { value: "individual", label: "Individual" },
  { value: "any", label: "Either" },
];

function money(n: number) {
  return "₦" + (n ?? 0).toLocaleString("en-NG", { maximumFractionDigits: 2 });
}

export default function WithholdingSettingsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [policy, setPolicy] = useState<WHTPolicy | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // The calculator. This is the part a finance officer trusts or does not:
  // they will check it against a number they already know.
  const [calc, setCalc] = useState({ gross: "", category: "", payee: "company" as PayeeType });
  const [result, setResult] = useState<WHTResult | null>(null);
  const [calcBusy, setCalcBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await getWhtPolicy();
      setPolicy(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the schedule.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Pull the org's real spend categories off the requisition workflow.
  useEffect(() => {
    (async () => {
      try {
        const { getWorkflow } = await import("@/lib/requisitionApi");
        const wf = await getWorkflow();
        setCategories(wf.allowed_categories ?? []);
      } catch {
        try {
          await listDepartments();
        } catch {
          /* leave categories empty — free text still works */
        }
      }
    })();
  }, []);

  function patch(changes: Partial<WHTPolicy>) {
    setPolicy((p) => (p ? { ...p, ...changes } : p));
    setSaved(false);
  }

  function patchRule(i: number, changes: Partial<WHTRule>) {
    setPolicy((p) => {
      if (!p) return p;
      const rules = [...p.rules];
      rules[i] = { ...rules[i], ...changes };
      return { ...p, rules };
    });
    setSaved(false);
  }

  function addRule() {
    setPolicy((p) =>
      p
        ? {
            ...p,
            rules: [
              ...p.rules,
              { category: categories[0] ?? "", rate_percent: 0, payee_type: "company", description: "" },
            ],
          }
        : p,
    );
    setSaved(false);
  }

  function removeRule(i: number) {
    setPolicy((p) => (p ? { ...p, rules: p.rules.filter((_, j) => j !== i) } : p));
    setSaved(false);
  }

  async function save() {
    if (!policy) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await setWhtPolicy(policy);
      setPolicy(updated);
      setSaved(true);
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  async function runCalc() {
    const gross = parseFloat(calc.gross);
    if (!gross || !calc.category) return;
    setCalcBusy(true);
    setResult(null);
    try {
      setResult(await previewWht(gross, calc.category, calc.payee));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not calculate.");
    } finally {
      setCalcBusy(false);
    }
  }

  const hasRules = (policy?.rules?.length ?? 0) > 0;

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
        <h1 className="text-xl font-semibold text-gray-900">Withholding tax</h1>
        <p className="mt-1 text-sm text-gray-500">
          Your schedule, entered from your auditor&apos;s rates. DOCex ships none of
          its own.
        </p>

        {error && (
          <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error}
          </p>
        )}

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading the schedule…
          </div>
        ) : !policy ? null : (
          <>
            {/* ── the switch ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={policy.enabled}
                  disabled={!isAdmin}
                  onChange={(e) => patch({ enabled: e.target.checked })}
                  className="mt-0.5 h-4 w-4 rounded border-gray-300"
                />
                <span>
                  <span className="text-sm font-medium text-gray-900">
                    Withhold tax on payments
                  </span>
                  <span className="mt-0.5 block text-xs text-gray-500">
                    Off until your rates are entered. With this off, every payment
                    goes out gross — which is correct, and is not the same as a rate
                    of zero.
                  </span>
                </span>
              </label>

              {policy.enabled && !hasRules && (
                <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  Switched on with no rules, so nothing will be withheld. Add at
                  least one rate below.
                </p>
              )}
            </section>

            {/* ── the rates ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-4">
                <h2 className="text-sm font-semibold text-gray-900">Rates</h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  One line per category. <strong>Payee type matters</strong> — Nigerian
                  rates commonly differ between companies and individuals for the same
                  service, and applying the company rate to an individual
                  over-deducts.
                </p>
              </div>

              {!hasRules ? (
                <p className="px-5 py-8 text-center text-sm text-gray-400">
                  No rates entered. Nothing is being withheld.
                </p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {policy.rules.map((r, i) => (
                    <div key={i} className="grid grid-cols-1 gap-2 px-5 py-3 sm:grid-cols-12">
                      <div className="sm:col-span-4">
                        {categories.length ? (
                          <select
                            value={r.category}
                            disabled={!isAdmin}
                            onChange={(e) => patchRule(i, { category: e.target.value })}
                            className={inputCls + " w-full"}
                          >
                            <option value="">Category…</option>
                            {categories.map((c) => (
                              <option key={c} value={c}>
                                {c.replace(/_/g, " ")}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            value={r.category}
                            disabled={!isAdmin}
                            onChange={(e) => patchRule(i, { category: e.target.value })}
                            placeholder="Category"
                            className={inputCls + " w-full"}
                          />
                        )}
                      </div>
                      <div className="sm:col-span-2">
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            step="0.5"
                            min="0"
                            max="100"
                            value={r.rate_percent}
                            disabled={!isAdmin}
                            onChange={(e) =>
                              patchRule(i, { rate_percent: parseFloat(e.target.value) || 0 })
                            }
                            className={inputCls + " w-full"}
                          />
                          <span className="text-sm text-gray-400">%</span>
                        </div>
                      </div>
                      <div className="sm:col-span-3">
                        <select
                          value={r.payee_type}
                          disabled={!isAdmin}
                          onChange={(e) =>
                            patchRule(i, { payee_type: e.target.value as PayeeType })
                          }
                          className={inputCls + " w-full"}
                        >
                          {PAYEE_TYPES.map((p) => (
                            <option key={p.value} value={p.value}>
                              {p.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="sm:col-span-3 flex items-center gap-2">
                        <input
                          value={r.description}
                          disabled={!isAdmin}
                          onChange={(e) => patchRule(i, { description: e.target.value })}
                          placeholder="Note (optional)"
                          className={inputCls + " w-full"}
                        />
                        {isAdmin && (
                          <button
                            type="button"
                            onClick={() => removeRule(i)}
                            title="Remove"
                            className="shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                      {r.rate_percent > 30 && (
                        <p className="sm:col-span-12 text-[11px] font-medium text-amber-700">
                          {r.rate_percent}% is unusually high — confirm against the
                          schedule before saving.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {isAdmin && (
                <div className="border-t border-gray-100 px-5 py-3">
                  <button
                    type="button"
                    onClick={addRule}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
                  >
                    <Plus className="h-4 w-4" /> Add a rate
                  </button>
                </div>
              )}
            </section>

            {/* ── where it goes ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900">Remittance</h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Withheld tax is a second real payment. Naming the authority means it
                appears on the ledger as a payee — not as an unexplained debit, which
                is the same shape as an unauthorised one.
              </p>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">Authority</span>
                  <input
                    value={policy.authority_name}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ authority_name: e.target.value })}
                    className={inputCls + " mt-1 w-full"}
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">
                    Account code
                  </span>
                  <input
                    value={policy.account_code}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ account_code: e.target.value })}
                    placeholder="e.g. 62010"
                    className={inputCls + " mt-1 w-full"}
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">
                    Minimum amount
                  </span>
                  <input
                    type="number"
                    min="0"
                    value={policy.minimum_amount}
                    disabled={!isAdmin}
                    onChange={(e) =>
                      patch({ minimum_amount: parseFloat(e.target.value) || 0 })
                    }
                    className={inputCls + " mt-1 w-full"}
                  />
                </label>
              </div>
            </section>

            {isAdmin && (
              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  onClick={save}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Save schedule
                </button>
                {saved && (
                  <span className="text-sm font-medium text-emerald-600">Saved.</span>
                )}
              </div>
            )}

            {/* ── the calculator ── */}
            <section className="mt-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                <Calculator className="h-4 w-4 text-gray-400" />
                Check a payment
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">
                What would be withheld, and why. Try it against an invoice you have
                already paid — the answer should match what you actually did.
              </p>

              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-4">
                <input
                  type="number"
                  value={calc.gross}
                  onChange={(e) => setCalc({ ...calc, gross: e.target.value })}
                  placeholder="Gross amount"
                  className={inputCls}
                />
                {categories.length ? (
                  <select
                    value={calc.category}
                    onChange={(e) => setCalc({ ...calc, category: e.target.value })}
                    className={inputCls}
                  >
                    <option value="">Category…</option>
                    {categories.map((c) => (
                      <option key={c} value={c}>
                        {c.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={calc.category}
                    onChange={(e) => setCalc({ ...calc, category: e.target.value })}
                    placeholder="Category"
                    className={inputCls}
                  />
                )}
                <select
                  value={calc.payee}
                  onChange={(e) => setCalc({ ...calc, payee: e.target.value as PayeeType })}
                  className={inputCls}
                >
                  {PAYEE_TYPES.filter((p) => p.value !== "any").map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={runCalc}
                  disabled={calcBusy || !calc.gross || !calc.category}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
                >
                  {calcBusy ? "Working…" : "Calculate"}
                </button>
              </div>

              {result && (
                <div className="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-4">
                  {result.applicable ? (
                    <>
                      <div className="grid grid-cols-3 gap-4 text-center">
                        <div>
                          <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Invoice
                          </p>
                          <p className="mt-0.5 text-lg font-semibold text-gray-900">
                            {money(result.gross)}
                          </p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Withheld ({result.rate_percent}%)
                          </p>
                          <p className="mt-0.5 text-lg font-semibold text-amber-700">
                            {money(result.withheld)}
                          </p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-wide text-gray-500">
                            Vendor receives
                          </p>
                          <p className="mt-0.5 text-lg font-semibold text-emerald-700">
                            {money(result.net)}
                          </p>
                        </div>
                      </div>
                      <p className="mt-3 border-t border-gray-200 pt-3 text-xs text-gray-600">
                        {result.reason}
                      </p>
                      <p className="mt-1 text-[11px] text-gray-500">
                        Both lines are recorded: the net to the vendor and the
                        remittance to {policy.authority_name}. Reconciliation matches
                        both, so neither looks like money nobody approved.
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-gray-600">
                      <strong>Nothing withheld.</strong> {result.reason}
                    </p>
                  )}
                </div>
              )}
            </section>

            {policy.note && (
              <p className="mt-6 rounded-lg bg-gray-50 px-4 py-3 text-xs leading-relaxed text-gray-500">
                {policy.note}
              </p>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
