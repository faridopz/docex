"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, Paperclip, Plus, Receipt, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { myOpenAdvances, type AdvanceRecord } from "@/lib/advancesApi";
import { lookupProject, type ProjectLookup } from "@/lib/projectsApi";
import {
  createRequisition,
  listRequisitions,
  newIdempotencyKey,
  submitRequisition,
  uploadRequisitionAttachment,
} from "@/lib/requisitionApi";
import { money, REQ_STATUS_LABEL, REQ_STATUS_STYLE, shortDate } from "@/lib/requisitionFormat";
import type { RequisitionSummary } from "@/types/requisition";

/**
 * Expense claims — claim back what you spent.
 *
 * A claim is a payment request like any other: the same checks, the same
 * approvers, the same voucher and audit trail. What's different is the shape
 * of the form, which follows how people actually remember spending: a list
 * of things, each with its receipt. The total is added up for you, and if
 * the claim settles an advance, the screen says straight away whether you'll
 * be paid the difference or owe some back.
 */

type Item = { date: string; description: string; budget_line: string; amount: string; file: File | null };

const blank = (): Item => ({ date: "", description: "", budget_line: "", amount: "", file: null });

export default function ClaimsPageWrapper() {
  // useSearchParams needs a Suspense boundary for the production build.
  return (
    <Suspense fallback={null}>
      <ClaimsPage />
    </Suspense>
  );
}

function ClaimsPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { user } = useAuth();
  const [claims, setClaims] = useState<RequisitionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const [purpose, setPurpose] = useState("");
  const [code, setCode] = useState("");
  const [project, setProject] = useState<ProjectLookup | null>(null);
  const [advances, setAdvances] = useState<AdvanceRecord[] | null>(null);
  const [advanceId, setAdvanceId] = useState("");
  const [items, setItems] = useState<Item[]>([blank()]);
  const [bank, setBank] = useState("");
  const [account, setAccount] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [key] = useState(() => newIdempotencyKey());

  const load = useCallback(async () => {
    try {
      const all = await listRequisitions();
      const me = (user?.email ?? "").toLowerCase();
      setClaims(all.filter((r) => r.kind === "expense_claim" && r.submitted_by.toLowerCase() === me));
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  useEffect(() => {
    if (adding && user) void myOpenAdvances(user.email).then(setAdvances);
  }, [adding, user]);

  // Arrived from "Settle with my receipts" on the Advances page: open the
  // form with that advance already chosen.
  useEffect(() => {
    const adv = params?.get("advance");
    if (adv) {
      setAdding(true);
      setAdvanceId(adv);
    }
  }, [params]);

  useEffect(() => {
    const c = code.trim();
    if (!c) {
      setProject(null);
      return;
    }
    const t = setTimeout(async () => setProject(await lookupProject(c)), 350);
    return () => clearTimeout(t);
  }, [code]);

  const total = useMemo(() => items.reduce((s, i) => s + (Number(i.amount) || 0), 0), [items]);
  const advance = advances?.find((a) => a.id === advanceId) ?? null;
  const diff = advance ? total - advance.amount : total;

  function patch(i: number, p: Partial<Item>) {
    setItems(items.map((x, j) => (j === i ? { ...x, ...p } : x)));
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const used = items.filter((i) => i.description.trim() || Number(i.amount) || i.file);
    const problems: string[] = [];
    if (!purpose.trim()) problems.push("Say what the spending was for.");
    if (used.length === 0) problems.push("Add at least one item.");
    used.forEach((it, n) => {
      if (!it.description.trim()) problems.push(`Item ${n + 1}: what was it?`);
      if (!(Number(it.amount) > 0)) problems.push(`Item ${n + 1}: how much?`);
      if (!it.file) problems.push(`Item ${n + 1}: attach its receipt.`);
    });
    if (diff > 0 && !account.trim()) problems.push("Give the account the money should go to.");
    if (problems.length) {
      setError(problems.join(" "));
      return;
    }
    try {
      setBusy("Saving your claim…");
      const draft = await createRequisition({
        kind: "expense_claim",
        vendor_name: user?.name ?? "",
        amount: 0,
        description: purpose.trim(),
        project_code: code.trim(),
        grant_code: project && project.found ? project.project_code : "",
        advance_id: advanceId || undefined,
        vendor_account: account.trim(),
        vendor_bank_name: bank.trim(),
        budget_lines: used.map((it) => ({
          description: it.description.trim(), unit: "", budget_line: it.budget_line.trim(),
          quantity: 1, frequency: 1, unit_cost: Number(it.amount), line_total: 0, date: it.date,
        })),
        submit: false,
      }, key);
      for (let n = 0; n < used.length; n++) {
        setBusy(`Attaching receipt ${n + 1} of ${used.length}…`);
        await uploadRequisitionAttachment(draft.id, used[n].file as File, `item-${n + 1}`);
      }
      setBusy("Sending for approval…");
      await submitRequisition(draft.id);
      router.push(`/requisitions/${draft.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the claim.");
      setBusy(null);
    }
  }

  const input = "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
  const label = "mb-1 block text-xs font-medium text-gray-600";

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Expense claims</h1>
            <p className="mt-1 text-sm text-gray-500">
              Claim back what you spent for work. List each thing with its receipt; it goes through the same approvals as any payment.
            </p>
          </div>
          {!adding && (
            <button onClick={() => setAdding(true)}
                    className="inline-flex shrink-0 items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
              <Plus className="h-4 w-4" /> New claim
            </button>
          )}
        </div>

        {adding && (
          <form onSubmit={send} className="mb-8 space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className={label}>What was it for?</label>
                <input className={input} value={purpose} onChange={(e) => setPurpose(e.target.value)}
                       placeholder="e.g. Field visit to Zaria clinics, 14–15 Sep" />
              </div>
              <div>
                <label className={label}>Project or grant code</label>
                <input className={input} value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. GF-TB-26" />
                {project && (
                  <p className={`mt-1 text-xs ${project.found ? "text-gray-500" : "text-amber-700"}`}>
                    {project.found ? `${project.donor}${project.title ? ` · ${project.title}` : ""}` : "No project with this code"}
                  </p>
                )}
              </div>
              {advances && advances.length > 0 && (
                <div>
                  <label className={label}>Does this settle an advance?</label>
                  <select className={input} value={advanceId} onChange={(e) => setAdvanceId(e.target.value)}>
                    <option value="">No</option>
                    {advances.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.ref} · {money(a.amount, a.currency)} · {a.purpose}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <section>
              <h2 className="mb-2 text-sm font-semibold text-gray-900">What you spent</h2>
              <div className="space-y-3">
                {items.map((it, i) => (
                  <div key={i} className="grid gap-2 rounded-lg border border-gray-100 bg-gray-50/60 p-3 sm:grid-cols-[8.5rem_1fr_7rem_8rem_auto]">
                    <input type="date" className={input} value={it.date} onChange={(e) => patch(i, { date: e.target.value })} aria-label="Date" />
                    <input className={input} value={it.description} onChange={(e) => patch(i, { description: e.target.value })}
                           placeholder="What was it? e.g. Taxi to the clinic" />
                    <input className={input} value={it.budget_line} onChange={(e) => patch(i, { budget_line: e.target.value })}
                           placeholder="Budget line" list="claim-budget-lines" />
                    <input className={input} inputMode="decimal" value={it.amount} onChange={(e) => patch(i, { amount: e.target.value })}
                           placeholder="Amount" />
                    <div className="flex items-center gap-1">
                      <label className={`inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-2 text-xs ${
                        it.file ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"}`}>
                        <Paperclip className="h-3.5 w-3.5" />
                        <span className="max-w-[7rem] truncate">{it.file ? it.file.name : "Receipt"}</span>
                        <input type="file" className="hidden" accept="image/*,application/pdf"
                               onChange={(e) => patch(i, { file: e.target.files?.[0] ?? null })} />
                      </label>
                      {items.length > 1 && (
                        <button type="button" onClick={() => setItems(items.filter((_, j) => j !== i))}
                                className="rounded-md p-2 text-gray-400 hover:text-red-600" aria-label="Remove item">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                <datalist id="claim-budget-lines">
                  {project && project.found
                    ? project.budget_lines.map((bl) => <option key={bl.code} value={bl.code}>{bl.label}</option>)
                    : null}
                </datalist>
                <button type="button" onClick={() => setItems([...items, blank()])}
                        className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
                  <Plus className="h-4 w-4" /> Add another item
                </button>
              </div>
            </section>

            <div className="rounded-lg bg-gray-50 p-4 text-sm">
              <div className="flex justify-between"><span className="text-gray-600">You spent</span><span className="font-medium">{money(total)}</span></div>
              {advance && (
                <>
                  <div className="flex justify-between"><span className="text-gray-600">Advance {advance.ref}</span><span>− {money(advance.amount, advance.currency)}</span></div>
                  <div className="mt-2 flex justify-between border-t border-gray-200 pt-2 font-semibold">
                    {diff > 0 ? (<><span>To be paid to you</span><span>{money(diff)}</span></>)
                      : diff < 0 ? (<><span className="text-amber-800">To return to the organisation</span><span className="text-amber-800">{money(-diff)}</span></>)
                      : (<><span>Nothing owed either way</span><span>{money(0)}</span></>)}
                  </div>
                </>
              )}
            </div>

            {diff > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className={label}>Your bank</label>
                  <input className={input} value={bank} onChange={(e) => setBank(e.target.value)} placeholder="e.g. GTBank" />
                </div>
                <div>
                  <label className={label}>Your account number</label>
                  <input className={input} inputMode="numeric" value={account} onChange={(e) => setAccount(e.target.value)} placeholder="10 digits" />
                </div>
              </div>
            )}

            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

            <div className="flex items-center justify-end gap-3">
              {busy && <span className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" />{busy}</span>}
              <button type="button" onClick={() => setAdding(false)} disabled={!!busy}
                      className="rounded-md px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">Cancel</button>
              <button type="submit" disabled={!!busy}
                      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                Send claim
              </button>
            </div>
          </form>
        )}

        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">My claims</h2>
        {loading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-gray-400"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        ) : claims.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-300 py-12 text-center">
            <Receipt className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-3 text-sm text-gray-600">No claims yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 bg-white shadow-sm">
            {claims.map((c) => (
              <Link key={c.id} href={`/requisitions/${c.id}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-gray-50">
                <div className="min-w-0">
                  <span className="font-medium text-gray-900">{c.ref}</span>
                  <span className="ml-2 text-gray-500">{shortDate(c.submitted_at)}</span>
                  <div className="text-xs text-gray-500">
                    Spent {money(c.claim_total ?? c.amount, c.currency)}
                    {c.advance_id ? ` · settles an advance · ${c.amount > 0 ? `${money(c.amount, c.currency)} to you` : "nothing to pay"}` : ""}
                  </div>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${REQ_STATUS_STYLE[c.status]}`}>
                  {REQ_STATUS_LABEL[c.status]}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
