"use client";

import { useMemo, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { money } from "@/lib/requisitionFormat";
import type { Agreement, BudgetLineIn, PlannedStaff, ProjectInput } from "@/lib/projectsApi";

/**
 * One form for a new project and for editing one. Plain words, the fields a
 * donor budget actually has, and the arithmetic shown as you type — so the
 * person setting it up sees "lines add up to ₦X of ₦Y" before the server has
 * to refuse anything.
 */
export function ProjectForm({
  initial,
  creating,
  busy,
  error,
  onSave,
  onCancel,
}: {
  initial?: Agreement;
  creating: boolean;
  busy: boolean;
  error: string | null;
  onSave: (body: ProjectInput) => void;
  onCancel: () => void;
}) {
  const [code, setCode] = useState(initial?.project_code ?? "");
  const [donor, setDonor] = useState(initial?.donor ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [value, setValue] = useState(initial ? String(initial.value || "") : "");
  const [currency, setCurrency] = useState(initial?.currency ?? "NGN");
  const [start, setStart] = useState(initial?.start_date ?? "");
  const [end, setEnd] = useState(initial?.end_date ?? "");
  const [status, setStatus] = useState<Agreement["status"]>(initial?.status ?? "active");
  const [lines, setLines] = useState<BudgetLineIn[]>(initial?.budget_lines ?? []);
  const [staff, setStaff] = useState<PlannedStaff[]>(initial?.staff ?? []);

  const budget = Number(value) || 0;
  const linesTotal = useMemo(() => lines.reduce((s, l) => s + (Number(l.amount) || 0), 0), [lines]);
  const over = lines.length > 0 && budget > 0 && linesTotal - budget > 0.01;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSave({
      ...(creating ? { project_code: code.trim() } : {}),
      donor: donor.trim(),
      title: title.trim(),
      value: budget,
      currency: currency.trim().toUpperCase() || "NGN",
      start_date: start || null,
      end_date: end || null,
      status,
      budget_lines: lines
        .filter((l) => l.code.trim() || l.label.trim() || Number(l.amount))
        .map((l) => ({ code: l.code.trim(), label: l.label.trim(), amount: Number(l.amount) || 0 })),
      staff: staff
        .filter((s) => s.name.trim())
        .map((s) => ({ ...s, name: s.name.trim(), percent: Number(s.percent) || 0 })),
    });
  }

  const input = "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";
  const label = "block text-xs font-medium text-gray-600 mb-1";

  return (
    <form onSubmit={submit} className="space-y-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={label}>Project code (what staff put on requests)</label>
          <input className={input} value={code} onChange={(e) => setCode(e.target.value)} disabled={!creating}
                 placeholder="e.g. GF-TB-26" required />
          {!creating && <p className="mt-1 text-xs text-gray-400">The code can&apos;t change: payments already carry it.</p>}
        </div>
        <div>
          <label className={label}>Donor</label>
          <input className={input} value={donor} onChange={(e) => setDonor(e.target.value)} placeholder="e.g. Global Fund" required />
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Project name</label>
          <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Community TB case finding" />
        </div>
        <div>
          <label className={label}>Total budget</label>
          <div className="flex gap-2">
            <input className={`${input} w-24`} value={currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Currency" />
            <input className={input} inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="0.00" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={label}>Starts</label>
            <input type="date" className={input} value={start ?? ""} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label className={label}>Ends</label>
            <input type="date" className={input} value={end ?? ""} onChange={(e) => setEnd(e.target.value)} />
          </div>
        </div>
        {!creating && (
          <div>
            <label className={label}>Status</label>
            <select className={input} value={status} onChange={(e) => setStatus(e.target.value as Agreement["status"])}>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="closed">Closed</option>
            </select>
          </div>
        )}
      </div>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Budget lines</h3>
          <span className={`text-xs ${over ? "font-medium text-red-600" : "text-gray-500"}`}>
            Lines add up to {money(linesTotal, currency)}{budget ? ` of ${money(budget, currency)}` : ""}
            {over ? " — more than the budget" : ""}
          </span>
        </div>
        <p className="mb-3 text-xs text-gray-500">
          Optional. Use the donor&apos;s own budget lines; staff pick one on a request and the system checks there is money left on it.
        </p>
        <div className="space-y-2">
          {lines.map((l, i) => (
            <div key={i} className="flex gap-2">
              <input className={`${input} w-28`} placeholder="Code" value={l.code}
                     onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, code: e.target.value } : x)))} />
              <input className={input} placeholder="What the donor budget calls it" value={l.label}
                     onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
              <input className={`${input} w-40`} inputMode="decimal" placeholder="Amount" value={l.amount || ""}
                     onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, amount: Number(e.target.value) || 0 } : x)))} />
              <button type="button" onClick={() => setLines(lines.filter((_, j) => j !== i))}
                      className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-red-600" aria-label="Remove line">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button type="button" onClick={() => setLines([...lines, { code: "", label: "", amount: 0 }])}
                  className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
            <Plus className="h-4 w-4" /> Add a budget line
          </button>
        </div>
      </section>

      <section>
        <h3 className="mb-1 text-sm font-semibold text-gray-900">Staff on this project</h3>
        <p className="mb-3 text-xs text-gray-500">
          Who the budget says works on it, and what share of their time. A plan: the hours actually worked come from approved timesheets.
        </p>
        <div className="space-y-2">
          {staff.map((s, i) => (
            <div key={i} className="flex gap-2">
              <input className={input} placeholder="Name" value={s.name}
                     onChange={(e) => setStaff(staff.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
              <input className={input} placeholder="Role" value={s.role ?? ""}
                     onChange={(e) => setStaff(staff.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))} />
              <input className={input} placeholder="Email (if they sign in)" value={s.staff_id ?? ""}
                     onChange={(e) => setStaff(staff.map((x, j) => (j === i ? { ...x, staff_id: e.target.value } : x)))} />
              <div className="flex w-28 items-center gap-1">
                <input className={input} inputMode="decimal" value={s.percent || ""} placeholder="%"
                       onChange={(e) => setStaff(staff.map((x, j) => (j === i ? { ...x, percent: Number(e.target.value) || 0 } : x)))} />
                <span className="text-sm text-gray-500">%</span>
              </div>
              <button type="button" onClick={() => setStaff(staff.filter((_, j) => j !== i))}
                      className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-red-600" aria-label="Remove person">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button type="button" onClick={() => setStaff([...staff, { name: "", role: "", staff_id: "", percent: 0 }])}
                  className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700">
            <Plus className="h-4 w-4" /> Add a person
          </button>
        </div>
      </section>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-md px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">
          Cancel
        </button>
        <button type="submit" disabled={busy || over}
                className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          {creating ? "Create project" : "Save changes"}
        </button>
      </div>
    </form>
  );
}

/** The used / committed / left bar every project shows. Widths are shares of
 *  the budget; anything over budget is shown in red rather than clipped. */
export function BudgetBar({ budget, used, committed }: { budget: number; used: number; committed: number }) {
  if (budget <= 0) return <div className="h-2 rounded-full bg-gray-100" />;
  const u = Math.min(100, (used / budget) * 100);
  const c = Math.min(100 - u, (committed / budget) * 100);
  const over = used + committed > budget + 0.005;
  return (
    <div className={`flex h-2 overflow-hidden rounded-full ${over ? "bg-red-100 ring-1 ring-red-300" : "bg-gray-100"}`}>
      <div className="bg-emerald-500" style={{ width: `${u}%` }} />
      <div className="bg-amber-400" style={{ width: `${c}%` }} />
    </div>
  );
}
