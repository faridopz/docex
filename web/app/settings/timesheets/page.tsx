"use client";

/**
 * Timesheet settings — one card.
 *
 * Timesheets are optional: an organisation that charges salaries to grants by
 * a fixed split never needs them, and this page says so plainly. One that does
 * charge by recorded effort (most donor-funded NGOs) decides here how staff
 * record, how long they have to fix a month, and who signs.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import { listDepartments } from "@/lib/erpApi";
import { getClientConfig, hasFeature, setClientConfig } from "@/lib/orgConfig";
import { getPolicy, savePolicy } from "@/lib/timesheetApi";
import type { TimesheetPolicy } from "@/types/timesheet";

type Span = "day" | "week" | "month";

export default function TimesheetSettingsPage() {
  const { user } = useAuth();
  const [on, setOn] = useState<boolean | null>(null);
  const [policy, setPolicy] = useState<TimesheetPolicy | null>(null);
  const [departments, setDepartments] = useState<{ key: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graceOn, setGraceOn] = useState(false);

  const load = useCallback(async () => {
    try {
      const cfg = await getClientConfig();
      const enabled = hasFeature(cfg, "timesheets");
      setOn(enabled);
      if (enabled) {
        const p = await getPolicy();
        setPolicy(p);
        setGraceOn(p.grace_days !== null && p.grace_days !== undefined);
      }
      const d = await listDepartments();
      setDepartments(d.departments.map((x) => ({ key: x.key, name: x.name })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the settings.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(next: boolean) {
    setBusy(true);
    setError(null);
    try {
      await setClientConfig({ features: { timesheets: next } });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change it.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!policy) return;
    if (!policy.allowed_spans.length) {
      setError("Choose at least one way for staff to record time.");
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setPolicy(await savePolicy({ ...policy, grace_days: graceOn ? policy.grace_days ?? 5 : null }));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const patch = (p: Partial<TimesheetPolicy>) => {
    setSaved(false);
    setPolicy((cur) => (cur ? { ...cur, ...p } : cur));
  };

  if (user && user.role !== "admin") {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl px-6 py-8 text-sm text-gray-600">Only an administrator can change timesheet settings.</div>
      </AppShell>
    );
  }

  const box = "rounded-xl border border-gray-200 bg-white p-5 shadow-sm";
  const h = "text-sm font-semibold text-gray-900";
  const hint = "mt-0.5 text-xs text-gray-500";
  const option = (active: boolean) =>
    `flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${active ? "border-blue-500 bg-blue-50/60" : "border-gray-200 hover:border-gray-300"}`;

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl space-y-5 px-6 py-8">
        <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800">
          <ArrowLeft className="h-4 w-4" /> Settings
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Timesheets</h1>
          <p className="mt-1 text-sm text-gray-500">
            Staff record the time they spend on each project. Approved time decides how much of each salary every grant pays
            for — which most donors require.
          </p>
        </div>

        {on === null ? (
          <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        ) : (
          <section className={box}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className={h}>Use timesheets</h2>
                <p className={hint}>
                  {on
                    ? "On. Staff see “What did you work on today?” on their home screen."
                    : "Off. Salaries are charged to grants by each person's fixed split instead. Switch on if your donors want recorded effort."}
                </p>
              </div>
              <button type="button" role="switch" aria-checked={on} disabled={busy} onClick={() => toggle(!on)}
                      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? "bg-blue-600" : "bg-gray-300"}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${on ? "left-5" : "left-0.5"}`} />
              </button>
            </div>
          </section>
        )}

        {on && policy && (
          <>
            <section className={box}>
              <h2 className={h}>How staff record time</h2>
              <p className={hint}>Tick every way you accept. Each month is recorded one way, so nothing is counted twice.</p>
              <div className="mt-3 space-y-2">
                {([
                  ["day", "By day", "The most precise; staff can tap “full day” or “half day” from their home screen."],
                  ["week", "By week", "Hours per project for each week, for people who don't track individual days."],
                  ["month", "As a monthly total", "Hours per project for the month."],
                ] as [Span, string, string][]).map(([key, label, desc]) => (
                  <label key={key} className={option(policy.allowed_spans.includes(key))}>
                    <input type="checkbox" className="mt-0.5" checked={policy.allowed_spans.includes(key)}
                           onChange={(e) => patch({ allowed_spans: e.target.checked
                             ? [...policy.allowed_spans, key]
                             : policy.allowed_spans.filter((x) => x !== key) })} />
                    <span><span className="font-medium text-gray-900">{label}</span><br /><span className="text-gray-500">{desc}</span></span>
                  </label>
                ))}
              </div>
              <div className="mt-4">
                <label className="block text-xs font-medium text-gray-600">A full month&apos;s working hours</label>
                <input type="number" min={1} value={policy.standard_hours_per_period}
                       onChange={(e) => patch({ standard_hours_per_period: Number(e.target.value) || 0 })}
                       className="mt-1 w-32 rounded-md border border-gray-300 px-3 py-2 text-sm" />
                <p className={hint}>A full day is this divided by the month&apos;s working days.</p>
              </div>
            </section>

            <section className={box}>
              <h2 className={h}>Who must send a timesheet</h2>
              <div className="mt-3 space-y-2">
                {([
                  ["everyone", "Everyone", "All staff (not administrator accounts)."],
                  ["project_staff", "Only project staff", "People named on a project's staff list."],
                ] as ["everyone" | "project_staff", string, string][]).map(([key, label, desc]) => (
                  <label key={key} className={option(policy.who_records === key)}>
                    <input type="radio" name="who" className="mt-0.5" checked={policy.who_records === key}
                           onChange={() => patch({ who_records: key })} />
                    <span><span className="font-medium text-gray-900">{label}</span><br /><span className="text-gray-500">{desc}</span></span>
                  </label>
                ))}
              </div>
              <p className={hint + " mt-2"}>This decides who appears on Finance&apos;s “haven&apos;t started” list and gets reminders.</p>
            </section>

            <section className={box}>
              <h2 className={h}>Closing a month</h2>
              <label className="mt-3 flex items-center gap-3 text-sm">
                <input type="checkbox" checked={graceOn} onChange={(e) => { setGraceOn(e.target.checked); setSaved(false); }} />
                <span>Stop staff changing a month</span>
                <input type="number" min={0} disabled={!graceOn} value={policy.grace_days ?? 5}
                       onChange={(e) => patch({ grace_days: Math.max(0, Number(e.target.value) || 0) })}
                       className="w-16 rounded-md border border-gray-300 px-2 py-1 text-sm disabled:bg-gray-50" />
                <span>days after it ends</span>
              </label>
              <p className={hint}>Finance can reopen one person&apos;s month for a few days if a correction is needed; it&apos;s recorded.</p>
            </section>

            <section className={box}>
              <h2 className={h}>Who signs</h2>
              <p className={hint}>The person&apos;s supervisor (an approver in their department) always signs first.</p>
              <label className="mt-3 block text-xs font-medium text-gray-600">Then also</label>
              <select value={policy.second_approval} onChange={(e) => patch({ second_approval: e.target.value })}
                      className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm">
                <option value="">Nobody else — the supervisor&apos;s signature is enough</option>
                {departments.map((d) => (
                  <option key={d.key} value={d.key}>An approver in {d.name}</option>
                ))}
              </select>
            </section>

            {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <div className="flex items-center justify-end gap-3">
              {saved && <span className="flex items-center gap-1 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Saved</span>}
              <button type="button" onClick={save} disabled={busy}
                      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        )}
        {!policy && error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      </div>
    </AppShell>
  );
}
