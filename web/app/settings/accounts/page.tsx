"use client";

/**
 * Bank accounts — the organisation's register.
 *
 * A donor-funded organisation usually holds one account per grant. Each
 * payment records which one it left from (chosen from the project code), and
 * each statement is reconciled against that account's payments only. This is
 * where an administrator lists them, once. Numbers are stored for matching
 * and shown masked everywhere.
 */
import { useCallback, useEffect, useState } from "react";
import { Landmark, Loader2, Plus } from "lucide-react";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { addBankAccount, listBankAccounts, setQuickBooksName, type BankAccount } from "@/lib/bankAccountsApi";

const EMPTY = { code: "", name: "", account_number: "", bank_name: "", project_code: "" };

export default function BankAccountsPage() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<BankAccount[] | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAccounts(await listBankAccounts());
    } catch (e) {
      setAccounts([]);
      setError(e instanceof Error ? e.message : "Could not load the accounts.");
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await addBankAccount(form);
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that account.");
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";
  const canAdd = form.name.trim() && form.account_number.replace(/\D/g, "").length >= 10;

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-6 py-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Bank accounts</h1>
          <p className="mt-1 text-sm text-gray-600">
            Each payment records the account it left from — picked automatically from its project
            code — and each month&rsquo;s statement is reconciled against that account only.
          </p>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white">
          {accounts === null ? (
            <p className="flex items-center gap-2 p-5 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          ) : accounts.length === 0 ? (
            <p className="p-5 text-sm text-gray-500">
              No accounts yet. With one account there is nothing to choose; add each account once
              your organisation holds more than one.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {accounts.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
                  <span className="flex items-center gap-2.5 text-sm">
                    <Landmark className="h-4 w-4 text-gray-400" />
                    <span className="font-medium text-gray-900">{a.label}</span>
                  </span>
                  <span className="text-xs text-gray-500">
                    {a.project_code ? `Project ${a.project_code}` : "No project — choose it when paying"}
                    {a.active ? "" : " · closed"}
                  </span>
                  <QuickBooksName account={a} canEdit={user?.role === "admin"} onSaved={load} />
                </li>
              ))}
            </ul>
          )}
        </div>

        {user?.role === "admin" ? (
          <form onSubmit={add} className="space-y-3 rounded-xl border border-gray-200 bg-white p-5">
            <p className="text-sm font-medium text-gray-900">Add an account</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <input className={input} placeholder="Name, e.g. CARE / FCDO" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <input className={input} placeholder="Your code, e.g. B24" value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })} />
              <input className={input} placeholder="Bank, e.g. GTBank" value={form.bank_name}
                onChange={(e) => setForm({ ...form, bank_name: e.target.value })} />
              <input className={input} placeholder="10-digit account number" inputMode="numeric"
                value={form.account_number}
                onChange={(e) => setForm({ ...form, account_number: e.target.value })} />
              <input className={input} placeholder="Project code it pays for (optional)" value={form.project_code}
                onChange={(e) => setForm({ ...form, project_code: e.target.value })} />
            </div>
            <p className="text-xs text-gray-500">
              The project code is what lets a payment find its account without anyone choosing.
              The full number is stored for matching statements and never shown again.
            </p>
            {error ? <p className="text-sm text-red-700">{error}</p> : null}
            <button
              type="submit"
              disabled={!canAdd || busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Add account
            </button>
          </form>
        ) : null}
      </div>
    </AppShell>
  );
}


/** This account's name in QuickBooks, edited in place. The QuickBooks files
 * credit payments to it; set once, next to the account it describes. */
function QuickBooksName({ account, canEdit, onSaved }: {
  account: BankAccount; canEdit: boolean; onSaved: () => Promise<void> | void;
}) {
  const [value, setValue] = useState(account.quickbooks_name ?? "");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const dirty = value.trim() !== (account.quickbooks_name ?? "");

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      await setQuickBooksName(account.id, value.trim());
      setNote("Saved");
      await onSaved();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex w-full items-center gap-2 pl-6 text-xs">
      <span className="shrink-0 text-gray-500">In QuickBooks:</span>
      {canEdit ? (
        <>
          <input
            className="min-w-0 flex-1 rounded-md border border-gray-300 px-2 py-1 text-xs"
            onChange={(e) => { setValue(e.target.value); setNote(null); }}
            placeholder="The account's exact name in your QuickBooks chart of accounts"
            value={value}
          />
          <button
            className="rounded-md border border-gray-300 px-2 py-1 font-medium text-gray-700 disabled:opacity-40"
            disabled={!dirty || busy}
            onClick={save}
            type="button"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </>
      ) : (
        <span className="text-gray-700">{account.quickbooks_name || "not set"}</span>
      )}
      {note ? <span className="text-gray-500">{note}</span> : null}
    </div>
  );
}
