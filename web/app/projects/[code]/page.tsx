"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, FileDown, Loader2, Pencil } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { BudgetBar, ProjectForm } from "@/components/erp/ProjectForm";
import { money, shortDate } from "@/lib/requisitionFormat";
import {
  downloadDonorReport,
  getProject,
  updateProject,
  type ProjectDetail,
  type ProjectInput,
} from "@/lib/projectsApi";

function periodLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  if (!y || !m) return period;
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
      {hint && <p className="mt-0.5 text-xs text-gray-500">{hint}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

const th = "px-3 py-2 text-left text-xs font-medium text-gray-500";
const td = "px-3 py-2 text-sm text-gray-800";
const tdNum = "px-3 py-2 text-right text-sm tabular-nums text-gray-800";

export default function ProjectPage() {
  const params = useParams<{ code: string }>();
  const code = decodeURIComponent(params.code);
  const [data, setData] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await getProject(code));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this project.");
    }
  }, [code]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(body: ProjectInput) {
    setBusy(true);
    setFormError(null);
    try {
      await updateProject(code, body);
      setEditing(false);
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function report() {
    setReportBusy(true);
    setReportError(null);
    try {
      await downloadDonorReport(code, from, to);
    } catch (e) {
      setReportError(e instanceof Error ? e.message : "Could not build the report.");
    } finally {
      setReportBusy(false);
    }
  }

  if (error) {
    return (
      <AppShell>
        <div className="mx-auto max-w-5xl px-6 py-8">
          <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        </div>
      </AppShell>
    );
  }
  if (!data) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 px-6 py-16 text-sm text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      </AppShell>
    );
  }

  const { agreement: ag, figures: f } = data;
  const used = f.paid + f.salary;
  const cur = f.currency;

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
        <Link href="/projects" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800">
          <ArrowLeft className="h-4 w-4" /> All projects
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{ag.donor}</div>
            <h1 className="text-xl font-semibold text-gray-900">
              {ag.project_code}
              {ag.title && <span className="font-normal text-gray-500"> · {ag.title}</span>}
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              {ag.start_date || ag.end_date ? `${shortDate(ag.start_date)} – ${shortDate(ag.end_date)}` : "No dates set"}
              {ag.status !== "active" && ` · ${ag.status}`}
            </p>
          </div>
          {data.can_edit && !editing && (
            <button onClick={() => setEditing(true)}
                    className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
              <Pencil className="h-4 w-4" /> Edit
            </button>
          )}
        </div>

        {editing && (
          <ProjectForm initial={ag} creating={false} busy={busy} error={formError} onSave={save}
                       onCancel={() => setEditing(false)} />
        )}

        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            {[
              ["Budget", f.budget],
              ["Payments", f.paid],
              ["Salaries", f.salary],
              ["On its way", f.committed],
              ["Left", f.remaining],
            ].map(([label, v]) => (
              <div key={label as string}>
                <dt className="text-xs text-gray-500">{label}</dt>
                <dd className={`mt-0.5 font-semibold tabular-nums ${label === "Left" && (v as number) < 0 ? "text-red-600" : "text-gray-900"}`}>
                  {money(v as number, cur)}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-4">
            <BudgetBar budget={f.budget} used={used} committed={f.committed} />
            <p className="mt-2 text-xs text-gray-500">
              <span className="mr-3"><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />Paid {f.used_percent != null ? `(${f.used_percent}%)` : ""}</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-400" />Requests on their way ({f.open_requests_count})</span>
            </p>
          </div>
          {f.other_currency.length > 0 && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Some requests on this project are in {f.other_currency.join(", ")}; they are not counted here, because converting
              them would need an exchange rate nobody has agreed.
            </p>
          )}
        </div>

        <Section title="Donor report" hint="One PDF for the donor: budget against actual, staff time, salaries, payments with vouchers, and every exception with its reason.">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-gray-600">From</label>
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
                     className="rounded-md border border-gray-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-600">To</label>
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
                     className="rounded-md border border-gray-300 px-3 py-2 text-sm" />
            </div>
            <button onClick={report} disabled={reportBusy}
                    className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {reportBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
              Download report
            </button>
            <span className="text-xs text-gray-400">Leave the dates empty for the whole project so far.</span>
          </div>
          {reportError && <p className="mt-3 text-sm text-red-600">{reportError}</p>}
        </Section>

        <Section title="Budget lines" hint={f.lines.length ? undefined : "No budget lines set. Add them with Edit to check spending line by line."}>
          {f.lines.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-100">
                <thead>
                  <tr>
                    <th className={th}>Line</th>
                    <th className={`${th} text-right`}>Budget</th>
                    <th className={`${th} text-right`}>Paid</th>
                    <th className={`${th} text-right`}>On its way</th>
                    <th className={`${th} text-right`}>Left</th>
                    <th className={`${th} w-40`} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {f.lines.map((l) => (
                    <tr key={l.code}>
                      <td className={td}>
                        {l.code === "__unassigned__" ? (
                          <span className="text-gray-500">{l.label}</span>
                        ) : (
                          <>
                            <span className="font-medium">{l.code}</span>
                            {l.label && <span className="text-gray-500"> · {l.label}</span>}
                          </>
                        )}
                      </td>
                      <td className={tdNum}>{l.code === "__unassigned__" ? "—" : money(l.budget, cur)}</td>
                      <td className={tdNum}>{money(l.paid, cur)}</td>
                      <td className={tdNum}>{money(l.committed, cur)}</td>
                      <td className={`${tdNum} ${l.remaining != null && l.remaining < 0 ? "text-red-600" : ""}`}>
                        {l.remaining == null ? "—" : money(l.remaining, cur)}
                      </td>
                      <td className="px-3 py-2">
                        {l.code !== "__unassigned__" && <BudgetBar budget={l.budget} used={l.paid} committed={l.committed} />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section title="Staff time" hint="Approved timesheets only: hours each person recorded on this project, and who signed them.">
          {ag.staff.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {ag.staff.map((s) => (
                <span key={s.name} className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
                  {s.name}{s.role ? ` · ${s.role}` : ""} · {s.percent}% planned
                </span>
              ))}
            </div>
          )}
          {data.approved_time.length === 0 ? (
            <p className="text-sm text-gray-500">No approved time recorded on this project yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-100">
                <thead>
                  <tr>
                    <th className={th}>Month</th>
                    <th className={th}>Person</th>
                    <th className={`${th} text-right`}>Hours</th>
                    <th className={`${th} text-right`}>Share of their time</th>
                    <th className={th}>Approved by</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.approved_time.map((r) => (
                    <tr key={r.timesheet_id}>
                      <td className={td}>{periodLabel(r.period)}</td>
                      <td className={td}>{r.staff_name}</td>
                      <td className={tdNum}>{r.hours}</td>
                      <td className={tdNum}>{r.share_percent}%</td>
                      <td className={td}>{r.approved_by} <span className="text-gray-400">{shortDate(r.approved_at)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.salary.length > 0 && (
            <div className="mt-6 overflow-x-auto">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Salary charged</h3>
              <table className="min-w-full divide-y divide-gray-100">
                <thead>
                  <tr>
                    <th className={th}>Month</th>
                    <th className={th}>Person</th>
                    <th className={`${th} text-right`}>Share</th>
                    <th className={`${th} text-right`}>Charged</th>
                    <th className={th}>Based on</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.salary.map((r) => (
                    <tr key={`${r.period}-${r.staff_id}`}>
                      <td className={td}>{periodLabel(r.period)}</td>
                      <td className={td}>{r.name}</td>
                      <td className={tdNum}>{r.percent}%</td>
                      <td className={tdNum}>{money(r.cost, cur)}</td>
                      <td className={td}>
                        {r.basis === "timesheet" ? "Approved hours" : (
                          <span className="text-amber-700">Budgeted split, not recorded hours</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section title="Payments" hint="Every payment charged to this project. Open one to see its approvals and documents.">
          {data.payments.length === 0 ? (
            <p className="text-sm text-gray-500">No payments yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-100">
                <thead>
                  <tr>
                    <th className={th}>Paid</th>
                    <th className={th}>Request</th>
                    <th className={th}>Payee</th>
                    <th className={th}>Voucher</th>
                    <th className={`${th} text-right`}>Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.payments.map((p) => (
                    <tr key={p.transaction_id}>
                      <td className={td}>{shortDate(p.paid_at)}</td>
                      <td className={td}>
                        <Link href={`/requisitions/${p.requisition_id}`} className="text-blue-600 hover:underline">
                          {p.requisition_ref}
                        </Link>
                        {p.exceptions > 0 && (
                          <span className="ml-2 rounded bg-purple-50 px-1.5 py-0.5 text-xs text-purple-700">
                            {p.exceptions} exception{p.exceptions > 1 ? "s" : ""}
                          </span>
                        )}
                      </td>
                      <td className={td}>{p.payee}</td>
                      <td className={td}>{p.voucher_number || <span className="text-gray-400">—</span>}</td>
                      <td className={tdNum}>{money(p.amount, p.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {data.exceptions.length > 0 && (
          <Section title="Exceptions" hint="Policy checks that someone with authority released, and the reason they gave.">
            <ul className="space-y-3">
              {data.exceptions.map((e, i) => (
                <li key={i} className="rounded-lg border border-purple-100 bg-purple-50/40 p-3 text-sm">
                  <div className="font-medium text-gray-900">
                    {e.requisition_ref} · {e.check}
                  </div>
                  <div className="mt-1 text-gray-700">&ldquo;{e.reason}&rdquo;</div>
                  <div className="mt-1 text-xs text-gray-500">
                    Released by {e.released_by}{e.authority ? ` (${e.authority})` : ""} · {money(e.amount, cur)} to {e.payee}
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>
    </AppShell>
  );
}
