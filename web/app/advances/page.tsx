"use client";

/**
 * Advances — who has money out, and who must retire it by when.
 *
 * Opened automatically when an advance request is paid (the org says which
 * categories are advances), so this list is complete without anyone typing
 * it. Worst first: the people to chase today, with the consequence the org's
 * own policy attaches spelled out on each row.
 *
 * Finance sees everyone and settles advances (never their own). Everyone
 * else sees their own, which is how a person learns an advance is due before
 * their next request is blocked for it.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Clock, Loader2, Receipt, Wallet } from "lucide-react";
import { getClientConfig, hasFeature } from "@/lib/orgConfig";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import {
  getAging,
  recoverAdvance,
  retireAdvance,
  writeOffAdvance,
  type Aging,
  type AgingRow,
} from "@/lib/advancesApi";
import { money } from "@/lib/requisitionFormat";

function dueLabel(r: AgingRow): { text: string; tone: string } {
  if (r.days_overdue > 0) return { text: `${r.days_overdue} day${r.days_overdue === 1 ? "" : "s"} late`, tone: "text-red-700" };
  if (r.days_overdue === 0) return { text: "Due today", tone: "text-red-700" };
  const left = -r.days_overdue;
  return { text: `Due in ${left} day${left === 1 ? "" : "s"}`, tone: left <= 2 ? "text-amber-700" : "text-gray-600" };
}

export default function AdvancesPage() {
  const { user } = useAuth();
  const [claimsOn, setClaimsOn] = useState(false);
  useEffect(() => {
    getClientConfig().then((c) => setClaimsOn(hasFeature(c, "expense_claims"))).catch(() => {});
  }, []);
  const [data, setData] = useState<Aging | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getAging());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load advances.");
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const finance = data?.sees_everyone ?? false;
  const isAdmin = user?.role === "admin";

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-6 py-6 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{finance ? "Advances" : "My advances"}</h1>
          <p className="mt-1 text-sm text-gray-600">
            {finance
              ? "Every advance not yet retired, most urgent first. Each one opened itself when its request was paid."
              : "Money you have been advanced and not yet retired. Retire each one with your receipts before it is due — an overdue advance stops your next payment."}
          </p>
        </div>

        {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

        {data === null && !error ? (
          <p className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </p>
        ) : null}

        {data ? (
          <>
            {!data.configured ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                Your organisation&rsquo;s retirement window isn&rsquo;t set, so nothing is being counted as late.
              </p>
            ) : null}

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Not yet retired</p>
                <p className="mt-1 text-lg font-semibold text-gray-900">{money(data.outstanding_value)}</p>
                <p className="text-xs text-gray-500">{data.outstanding} advance{data.outstanding === 1 ? "" : "s"}</p>
              </div>
              <div className={`rounded-xl border p-4 ${data.overdue ? "border-red-200 bg-red-50" : "border-gray-200 bg-white"}`}>
                <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Overdue</p>
                <p className={`mt-1 text-lg font-semibold ${data.overdue ? "text-red-800" : "text-gray-900"}`}>
                  {money(data.overdue_value)}
                </p>
                <p className="text-xs text-gray-500">{data.overdue} advance{data.overdue === 1 ? "" : "s"}</p>
              </div>
            </div>

            <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white">
              {data.rows.length === 0 ? (
                <p className="flex items-center gap-2 p-5 text-sm text-gray-600">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  {finance ? "Nothing outstanding. Every advance is retired." : "You have no advances to retire."}
                </p>
              ) : (
                data.rows.map((r) => {
                  const due = dueLabel(r);
                  const mine = (user?.email || "").toLowerCase() === r.staff_id.toLowerCase();
                  return (
                    <div key={r.id} className="p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900">
                            {r.ref} · {finance ? r.staff_name : r.purpose}
                          </p>
                          <p className="mt-0.5 text-xs text-gray-500">
                            {finance ? `${r.purpose} · ` : ""}
                            {r.project_code ? `${r.project_code} · ` : ""}due {r.due_at}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-gray-900">{money(r.amount, r.currency)}</p>
                          <p className={`flex items-center justify-end gap-1 text-xs font-medium ${due.tone}`}>
                            {r.days_overdue >= 0 ? <AlertTriangle className="h-3.5 w-3.5" /> : <Clock className="h-3.5 w-3.5" />}
                            {due.text}
                          </p>
                        </div>
                      </div>
                      {r.escalation > 0 && r.consequence ? (
                        <p className="mt-2 rounded-md bg-red-50 px-2.5 py-1.5 text-xs text-red-800">{r.consequence}</p>
                      ) : null}
                      {finance && !mine ? (
                        open === r.id ? (
                          <SettlePanel row={r} isAdmin={isAdmin} onDone={async () => { setOpen(null); await load(); }} onCancel={() => setOpen(null)} />
                        ) : (
                          <button
                            type="button"
                            onClick={() => setOpen(r.id)}
                            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                          >
                            <Wallet className="h-3.5 w-3.5" /> Settle
                          </button>
                        )
                      ) : null}
                      {mine && claimsOn ? (
                        <Link href={`/claims?advance=${encodeURIComponent(r.id)}`}
                              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">
                          <Receipt className="h-3.5 w-3.5" /> Settle with my receipts
                        </Link>
                      ) : finance && mine ? (
                        <p className="mt-2 text-xs text-gray-500">Your own advance — someone else in Finance settles it.</p>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>

            {!finance ? (
              <p className="text-xs text-gray-500">
                {claimsOn
                  ? "To retire an advance, list what you spent with a receipt for each item. The difference is paid to you, or shown as what to return. "
                  : "To retire an advance, give Finance your receipts and any unspent balance. "}
                Raising a new
                request? <Link href="/requisitions/new" className="text-brand-700 underline">Start here</Link>.
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function SettlePanel({ row, isAdmin, onDone, onCancel }: {
  row: AgingRow; isAdmin: boolean; onDone: () => Promise<void>; onCancel: () => void;
}) {
  const [how, setHow] = useState<"retire" | "recover" | "writeoff">("retire");
  const [spent, setSpent] = useState(String(row.amount));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const spentNum = Number(spent.replace(/,/g, ""));
  const balance = row.amount - (Number.isFinite(spentNum) ? spentNum : 0);
  const ready = how === "retire" ? Number.isFinite(spentNum) && spentNum >= 0 : reason.trim().length >= 5;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      if (how === "retire") await retireAdvance(row.id, spentNum);
      else if (how === "recover") await recoverAdvance(row.id, reason.trim());
      else await writeOffAdvance(row.id, reason.trim());
      await onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't save.");
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";
  return (
    <div className="mt-3 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-1.5"><input type="radio" checked={how === "retire"} onChange={() => setHow("retire")} /> Retired with receipts</label>
        <label className="flex items-center gap-1.5"><input type="radio" checked={how === "recover"} onChange={() => setHow("recover")} /> Recovered from salary</label>
        {isAdmin ? (
          <label className="flex items-center gap-1.5"><input type="radio" checked={how === "writeoff"} onChange={() => setHow("writeoff")} /> Write off</label>
        ) : null}
      </div>
      {how === "retire" ? (
        <div>
          <label className="text-xs font-medium text-gray-700">Amount spent, per the receipts</label>
          <input value={spent} onChange={(e) => setSpent(e.target.value)} inputMode="decimal" className={input} />
          <p className="mt-1 text-xs text-gray-600">
            {Math.abs(balance) < 0.005
              ? "Fully spent — nothing to return or reimburse."
              : balance > 0
                ? `${money(balance, row.currency)} unspent — to be returned by ${row.staff_name}.`
                : `${money(-balance, row.currency)} overspent — to be reimbursed to ${row.staff_name}.`}
          </p>
        </div>
      ) : (
        <div>
          <label className="text-xs font-medium text-gray-700">
            {how === "recover" ? "Which payroll, and any note" : "Why the organisation is absorbing this"}
          </label>
          <input value={reason} onChange={(e) => setReason(e.target.value)} className={input} />
        </div>
      )}
      {error ? <p className="text-xs text-red-700">{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" disabled={!ready || busy} onClick={go}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100">
          Cancel
        </button>
      </div>
    </div>
  );
}
