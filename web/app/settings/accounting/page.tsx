"use client";

/**
 * QuickBooks settings.
 *
 * DOCex is not a general ledger — it owns approval and evidence; QuickBooks
 * owns the books. This screen holds the ONE thing a human must enter: how
 * DOCex spend categories and project/grant codes map to this organisation's
 * chart of accounts and classes (an invented mapping posts money to the wrong
 * account, which is worse than a failed import), plus which QuickBooks they
 * run. The monthly files themselves come from closing the month in
 * Reconciliation, so the books only receive payments that were approved AND
 * confirmed by the bank.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Banknote,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { getWorkflow } from "@/lib/requisitionApi";
import {
  getAccountMap,
  setAccountMap,
  type AccountMap,
} from "@/lib/accountingApi";

const inputCls =
  "rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-brand-400";

export default function AccountingSettingsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [map, setMap] = useState<AccountMap | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, wf] = await Promise.all([getAccountMap(), getWorkflow().catch(() => null)]);
      setMap(m);
      if (wf) setCategories(wf.allowed_categories ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the mapping.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function patch(changes: Partial<AccountMap>) {
    setMap((m) => (m ? { ...m, ...changes } : m));
    setSaved(false);
  }

  function accountRows(): [string, string][] {
    return Object.entries(map?.accounts ?? {});
  }
  function classRows(): [string, string][] {
    return Object.entries(map?.classes ?? {});
  }

  function setAccountRow(i: number, key: string, value: string) {
    const rows = accountRows();
    rows[i] = [key, value];
    patch({ accounts: Object.fromEntries(rows) });
  }
  function removeAccountRow(i: number) {
    const rows = accountRows().filter((_, j) => j !== i);
    patch({ accounts: Object.fromEntries(rows) });
  }
  function addAccountRow() {
    const rows = accountRows();
    rows.push([categories.find((c) => !rows.some(([k]) => k === c)) ?? "", ""]);
    patch({ accounts: Object.fromEntries(rows) });
  }

  function setClassRow(i: number, key: string, value: string) {
    const rows = classRows();
    rows[i] = [key, value];
    patch({ classes: Object.fromEntries(rows) });
  }
  function removeClassRow(i: number) {
    const rows = classRows().filter((_, j) => j !== i);
    patch({ classes: Object.fromEntries(rows) });
  }
  function addClassRow() {
    const rows = classRows();
    rows.push(["", ""]);
    patch({ classes: Object.fromEntries(rows) });
  }

  async function save() {
    if (!map) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await setAccountMap(map);
      setMap(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the mapping.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-4 py-8 md:px-8">
        <h1 className="text-xl font-semibold text-gray-900">QuickBooks handoff</h1>
        <p className="mt-1 text-sm text-gray-500">
          DOCex owns approval and evidence; QuickBooks owns the books. This maps your
          categories and projects to your chart of accounts, then exports what's
          approved — never guessed.
        </p>

        {error && (
          <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error}
          </p>
        )}

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading your mapping…
          </div>
        ) : !map ? null : (
          <>
            {/* ── account mapping ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-4">
                <h2 className="text-sm font-semibold text-gray-900">Category → account</h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  Every DOCex spend category maps to a QuickBooks expense account name.
                  Anything unmapped posts to the default below — visible, never dropped.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {accountRows().length === 0 && (
                  <p className="px-5 py-8 text-center text-sm text-gray-400">
                    No categories mapped yet.
                  </p>
                )}
                {accountRows().map(([cat, acct], i) => (
                  <div key={i} className="grid grid-cols-1 gap-2 px-5 py-3 sm:grid-cols-12">
                    <div className="sm:col-span-5">
                      {categories.length ? (
                        <select
                          value={cat}
                          disabled={!isAdmin}
                          onChange={(e) => setAccountRow(i, e.target.value, acct)}
                          className={inputCls + " w-full"}
                        >
                          <option value="">Category…</option>
                          {categories.map((c) => (
                            <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          value={cat}
                          disabled={!isAdmin}
                          onChange={(e) => setAccountRow(i, e.target.value, acct)}
                          placeholder="Category"
                          className={inputCls + " w-full"}
                        />
                      )}
                    </div>
                    <div className="sm:col-span-6 flex items-center gap-2">
                      <input
                        value={acct}
                        disabled={!isAdmin}
                        onChange={(e) => setAccountRow(i, cat, e.target.value)}
                        placeholder="QuickBooks account name"
                        className={inputCls + " w-full"}
                      />
                      {isAdmin && (
                        <button type="button" onClick={() => removeAccountRow(i)}
                          className="shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-red-50 hover:text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {isAdmin && (
                <div className="border-t border-gray-100 px-5 py-3">
                  <button type="button" onClick={addAccountRow}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50">
                    <Plus className="h-4 w-4" /> Map a category
                  </button>
                </div>
              )}
              <div className="border-t border-gray-100 px-5 py-4">
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">Default account (for anything unmapped)</span>
                  <input
                    value={map.default_account}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ default_account: e.target.value })}
                    className={inputCls + " mt-1 w-full sm:w-80"}
                  />
                </label>
              </div>
            </section>

            {/* ── class / grant mapping ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-5 py-4">
                <h2 className="text-sm font-semibold text-gray-900">Project/grant → class</h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  Tracks spend per grant in QuickBooks. Left blank, a payment still
                  exports — just with no Class, so per-donor reports won't include it.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {classRows().length === 0 && (
                  <p className="px-5 py-8 text-center text-sm text-gray-400">
                    No project/grant codes mapped yet.
                  </p>
                )}
                {classRows().map(([code, klass], i) => (
                  <div key={i} className="grid grid-cols-1 gap-2 px-5 py-3 sm:grid-cols-12">
                    <div className="sm:col-span-5">
                      <input
                        value={code}
                        disabled={!isAdmin}
                        onChange={(e) => setClassRow(i, e.target.value, klass)}
                        placeholder="Project or grant code, e.g. B4"
                        className={inputCls + " w-full"}
                      />
                    </div>
                    <div className="sm:col-span-6 flex items-center gap-2">
                      <input
                        value={klass}
                        disabled={!isAdmin}
                        onChange={(e) => setClassRow(i, code, e.target.value)}
                        placeholder="QuickBooks Class name"
                        className={inputCls + " w-full"}
                      />
                      {isAdmin && (
                        <button type="button" onClick={() => removeClassRow(i)}
                          className="shrink-0 rounded-lg p-2 text-gray-400 transition hover:bg-red-50 hover:text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {isAdmin && (
                <div className="border-t border-gray-100 px-5 py-3">
                  <button type="button" onClick={addClassRow}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50">
                    <Plus className="h-4 w-4" /> Map a project/grant
                  </button>
                </div>
              )}
              <div className="border-t border-gray-100 px-5 py-4">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={map.grant_as_customer}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ grant_as_customer: e.target.checked })}
                  />
                  Track grants as Customers/Jobs instead of Classes
                </label>
              </div>
            </section>

            {/* ── which QuickBooks ── */}
            <section className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900">Your QuickBooks</h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Decides which files DOCex gives you. The international edition of QuickBooks Online
                (used in Nigeria) can import bank transactions but not journals, so it gets the coded
                bank file; the US edition and Desktop can also import journals.
              </p>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">Edition</span>
                  <select
                    value={map.edition || "online_international"}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ edition: e.target.value })}
                    className={inputCls + " mt-1 w-full"}
                  >
                    <option value="online_international">QuickBooks Online — international</option>
                    <option value="online_us">QuickBooks Online — US</option>
                    <option value="desktop">QuickBooks Desktop</option>
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">Bank charges account</span>
                  <input
                    value={map.bank_charges_account ?? "Bank charges"}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ bank_charges_account: e.target.value })}
                    placeholder="e.g. Bank charges"
                    className={inputCls + " mt-1 w-full"}
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-medium text-gray-600">Date format on your import screen</span>
                  <select
                    value={map.date_format}
                    disabled={!isAdmin}
                    onChange={(e) => patch({ date_format: e.target.value })}
                    className={inputCls + " mt-1 w-full"}
                  >
                    <option value="%d/%m/%Y">DD/MM/YYYY</option>
                    <option value="%m/%d/%Y">MM/DD/YYYY</option>
                    <option value="%Y-%m-%d">YYYY-MM-DD</option>
                  </select>
                </label>
              </div>
              <p className="mt-3 text-xs text-gray-500">
                Each bank account&rsquo;s name in QuickBooks is set once, with the account, in{" "}
                <Link href="/settings/accounts" className="text-brand-700 underline">Settings → Bank accounts</Link>.
              </p>
            </section>

            {isAdmin && (
              <div className="mt-4 flex items-center gap-3">
                <button type="button" onClick={save} disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save mapping
                </button>
                {saved && <span className="text-sm font-medium text-emerald-600">Saved.</span>}
              </div>
            )}

            {/* ── where the files come from ── */}
            <section className="mt-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                <Banknote className="h-4 w-4 text-gray-400" /> Your monthly QuickBooks files
              </h2>
              <p className="mt-1 text-sm text-gray-600">
                They come from closing the month, so QuickBooks only ever receives payments that were
                approved in DOCex <em>and</em> confirmed by the bank. Upload the statement in{" "}
                <Link href="/reconciliation" className="text-brand-700 underline">Reconciliation</Link>,
                explain anything unmatched, close the month — then <span className="font-medium">Send to QuickBooks</span>.
              </p>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
