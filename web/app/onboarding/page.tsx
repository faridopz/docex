"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, Loader2, Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Page } from "@/components/layout/Page";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { humanise, money } from "@/lib/requisitionFormat";
import {
  applyWizard,
  getWizardAnswers,
  previewWizard,
  type WizardAnswers,
  type WizardPreview,
} from "@/lib/onboardingApi";

/**
 * /onboarding — set up any organisation's payment approvals with six plain
 * questions (setup_wizard.py does the work; this screen only asks).
 *
 * Every answer starts from the organisation's current setup, or the common
 * NGO arrangement for a new one, so most admins confirm rather than type.
 * Nothing is saved until "Save this setup" on the last screen, and the server
 * refuses — with nothing written — anything that would strand a waiting
 * request or a person.
 */

const STEPS = [
  "Your organisation",
  "Departments",
  "Who approves first",
  "Policy check",
  "Sign-off",
  "Paperwork",
  "Check and save",
] as const;

const CURRENCIES = ["NGN", "USD", "GHS", "KES", "UGX", "TZS", "ZAR", "GBP", "EUR"];
const COMMON_DOCS = [
  "memo", "invoice", "receipt", "purchase_order", "grn", "contract",
  "attendance_list", "payment_sheet", "activity_report", "travel_approval_form",
];

function slug(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function numOrNull(v: string): number | null {
  const n = Number(v.replace(/[^0-9.]/g, ""));
  return v.trim() === "" || Number.isNaN(n) ? null : n;
}

export default function SetupWizardPage() {
  const { ready, user } = useAuth();
  const [step, setStep] = useState(0);
  const [a, setA] = useState<WizardAnswers | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [preview, setPreview] = useState<WizardPreview | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [newDoc, setNewDoc] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!ready || user?.role !== "admin") return;
    getWizardAnswers()
      .then((r) => {
        setA(r.answers);
        setCategories(r.categories);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "Could not load your setup."));
  }, [ready, user?.role]);

  // Keep the preview current, a moment after each change.
  useEffect(() => {
    if (!a) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      previewWizard(a).then(setPreview).catch(() => undefined);
    }, 350);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [a]);

  const set = useCallback(<K extends keyof WizardAnswers>(k: K, v: WizardAnswers[K]) => {
    setSaved(false);
    setA((prev) => (prev ? { ...prev, [k]: v } : prev));
  }, []);

  const depts = useMemo(
    () => (a?.departments ?? []).filter((d) => d.name.trim()).map((d) => ({ key: d.key || slug(d.name), name: d.name })),
    [a?.departments],
  );
  const cur = a?.currency ?? "NGN";

  async function save() {
    if (!a) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await applyWizard(a);
      setPreview(res);
      setSaved(true);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Could not save. Nothing was changed.");
    } finally {
      setSaving(false);
    }
  }

  if (ready && user?.role !== "admin") {
    return (
      <AppShell>
        <Page width="narrow" title="Set up your organisation">
          <p className="text-sm text-gray-600">Only an administrator can change how approvals work.</p>
        </Page>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <Page
        width="narrow"
        title="Set up your organisation"
        subtitle="Six questions about how payments are approved where you work. You can come back and change any answer."
      >
        <ol className="flex flex-wrap gap-1.5">
          {STEPS.map((label, i) => (
            <li key={label}>
              <button
                type="button"
                onClick={() => setStep(i)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition",
                  i === step ? "bg-brand-600 text-white" : i < step ? "bg-brand-50 text-brand-700" : "bg-gray-100 text-gray-500",
                )}
              >
                {i < 6 ? `${i + 1}. ` : ""}
                {label}
              </button>
            </li>
          ))}
        </ol>

        {loadError ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{loadError}</div>
        ) : !a ? (
          <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading your current setup…
          </div>
        ) : (
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            {step === 0 && (
              <Section q="What is your organisation called?" help="This goes on the letterhead of every payment voucher.">
                <Field label="Organisation name">
                  <input className={inputCls} value={a.org_name} onChange={(e) => set("org_name", e.target.value)} placeholder="e.g. Hope Clinic Trust" />
                </Field>
                <Field label="Currency you pay in">
                  <select className={inputCls} value={a.currency} onChange={(e) => set("currency", e.target.value)}>
                    {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Address (one line per row)">
                  <textarea
                    className={inputCls}
                    rows={3}
                    value={a.address_lines.join("\n")}
                    onChange={(e) => set("address_lines", e.target.value.split("\n"))}
                  />
                </Field>
                <Field label="Registration number (optional)">
                  <input className={inputCls} value={a.rc_number} onChange={(e) => set("rc_number", e.target.value)} />
                </Field>
              </Section>
            )}

            {step === 1 && (
              <Section q="Which departments do you have?" help="Include every department that raises or approves payments. Rename or remove any that don't fit.">
                <ul className="space-y-2">
                  {a.departments.map((d, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <input
                        className={inputCls}
                        value={d.name}
                        onChange={(e) =>
                          set("departments", a.departments.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                        }
                      />
                      <button
                        type="button"
                        aria-label={`Remove ${d.name}`}
                        onClick={() => set("departments", a.departments.filter((_, j) => j !== i))}
                        className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </li>
                  ))}
                </ul>
                <button type="button" onClick={() => set("departments", [...a.departments, { name: "" }])} className={ghostBtn}>
                  <Plus className="h-4 w-4" /> Add a department
                </button>
              </Section>
            )}

            {step === 2 && (
              <Section q="When someone raises a payment request, who approves it first?" help="Most NGOs start with the requester's own manager, who confirms the need is real.">
                <Choice
                  checked={a.first_approver === "budget_holder"}
                  onChange={() => set("first_approver", "budget_holder")}
                  title="The requester's own manager (budget holder)"
                  text="A Programmes request goes to the Programme Manager, an HR request to the HR head. If the manager raises it themselves, it goes straight on."
                />
                <Choice
                  checked={a.first_approver === "department"}
                  onChange={() => set("first_approver", "department")}
                  title="Always the same department"
                  text="Every request starts with one department, whoever raised it."
                >
                  {a.first_approver === "department" && (
                    <select className={cn(inputCls, "mt-2")} value={a.first_department} onChange={(e) => set("first_department", e.target.value)}>
                      <option value="">Choose a department…</option>
                      {depts.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}
                    </select>
                  )}
                </Choice>
                <Choice
                  checked={a.first_approver === "none"}
                  onChange={() => set("first_approver", "none")}
                  title="Nobody. It goes straight to the policy check"
                  text="For small teams where the finance check is the first look."
                />
              </Section>
            )}

            {step === 3 && (
              <Section q="Who checks each request against your policies?" help="They check the documents, the budget line and the calculations. Usually Finance.">
                <Field label="Department">
                  <select className={inputCls} value={a.policy_department} onChange={(e) => set("policy_department", e.target.value)}>
                    <option value="">Choose a department…</option>
                    {depts.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}
                  </select>
                </Field>
                <Release
                  can={a.policy_can_release}
                  limit={a.policy_release_limit}
                  currency={cur}
                  onCan={(v) => set("policy_can_release", v)}
                  onLimit={(v) => set("policy_release_limit", v)}
                />
              </Section>
            )}

            {step === 4 && (
              <Section
                q="Who signs off after the policy check, and from what amount?"
                help="List them in order. Put 0 for someone who signs off on everything, or an amount for someone who only sees larger payments."
              >
                <ul className="space-y-3">
                  {a.signoffs.map((so, i) => (
                    <li key={i} className="rounded-xl border border-gray-200 p-3.5">
                      <div className="flex flex-wrap items-end gap-3">
                        <Field label={`Sign-off ${i + 1}`}>
                          <select
                            className={inputCls}
                            value={so.department}
                            onChange={(e) => set("signoffs", a.signoffs.map((x, j) => (j === i ? { ...x, department: e.target.value } : x)))}
                          >
                            <option value="">Choose…</option>
                            {depts.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}
                          </select>
                        </Field>
                        <Field label={`From (${cur})`}>
                          <input
                            className={inputCls}
                            inputMode="numeric"
                            value={so.from_amount ?? ""}
                            onChange={(e) => set("signoffs", a.signoffs.map((x, j) => (j === i ? { ...x, from_amount: numOrNull(e.target.value) } : x)))}
                          />
                        </Field>
                        <button
                          type="button"
                          aria-label="Remove this sign-off"
                          onClick={() => set("signoffs", a.signoffs.filter((_, j) => j !== i))}
                          className="mb-0.5 rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <p className="mt-1 text-xs text-gray-500">
                        {so.from_amount ? `Only requests of ${money(so.from_amount, cur)} and above.` : "Every request."}
                      </p>
                      <Release
                        can={so.can_release}
                        limit={so.release_limit}
                        currency={cur}
                        onCan={(v) => set("signoffs", a.signoffs.map((x, j) => (j === i ? { ...x, can_release: v } : x)))}
                        onLimit={(v) => set("signoffs", a.signoffs.map((x, j) => (j === i ? { ...x, release_limit: v } : x)))}
                      />
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => set("signoffs", [...a.signoffs, { department: "", from_amount: 0, can_release: false, release_limit: null }])}
                  className={ghostBtn}
                >
                  <Plus className="h-4 w-4" /> Add a sign-off
                </button>
              </Section>
            )}

            {step === 5 && (
              <Section q="What paperwork does every request need?" help="Tick what staff must attach. You can add your own.">
                <div className="flex flex-wrap gap-2">
                  {Array.from(new Set([...COMMON_DOCS, ...a.documents])).map((d) => {
                    const on = a.documents.includes(d);
                    return (
                      <button
                        key={d}
                        type="button"
                        onClick={() => set("documents", on ? a.documents.filter((x) => x !== d) : [...a.documents, d])}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm",
                          on ? "border-brand-300 bg-brand-50 text-brand-800" : "border-gray-200 text-gray-600 hover:bg-gray-50",
                        )}
                      >
                        {on ? <Check className="h-3.5 w-3.5" /> : null}
                        {humanise(d)}
                      </button>
                    );
                  })}
                </div>
                <div className="flex gap-2">
                  <input className={inputCls} value={newDoc} onChange={(e) => setNewDoc(e.target.value)} placeholder="Another document, e.g. Delivery note" />
                  <button
                    type="button"
                    className={ghostBtn}
                    onClick={() => {
                      const k = newDoc.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
                      if (k && !a.documents.includes(k)) set("documents", [...a.documents, k]);
                      setNewDoc("");
                    }}
                  >
                    <Plus className="h-4 w-4" /> Add
                  </button>
                </div>

                <div className="mt-2 border-t border-gray-100 pt-4">
                  <p className="text-sm font-medium text-gray-900">Quotes for purchases</p>
                  <p className="mb-2 text-xs text-gray-500">Leave blank if you don&rsquo;t require quotes.</p>
                  <div className="flex flex-wrap items-end gap-3">
                    <Field label="Number of quotes">
                      <select className={inputCls} value={a.quotes_count} onChange={(e) => set("quotes_count", Number(e.target.value))}>
                        {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </Field>
                    <Field label={`From (${cur})`}>
                      <input className={inputCls} inputMode="numeric" value={a.quotes_from ?? ""} onChange={(e) => set("quotes_from", numOrNull(e.target.value))} />
                    </Field>
                    <Field label={`Competitive tender from (${cur})`}>
                      <input className={inputCls} inputMode="numeric" value={a.tender_from ?? ""} onChange={(e) => set("tender_from", numOrNull(e.target.value))} />
                    </Field>
                  </div>
                  {a.quotes_from != null || a.tender_from != null ? (
                    <>
                      <p className="mb-1.5 mt-3 text-xs font-medium text-gray-700">Which kinds of payment are purchases (need quotes)?</p>
                      <div className="flex flex-wrap gap-2">
                        {categories.map((c) => {
                          const on = a.quote_categories.includes(c);
                          return (
                            <button
                              key={c}
                              type="button"
                              onClick={() => set("quote_categories", on ? a.quote_categories.filter((x) => x !== c) : [...a.quote_categories, c])}
                              className={cn(
                                "rounded-full border px-3 py-1 text-xs",
                                on ? "border-brand-300 bg-brand-50 text-brand-800" : "border-gray-200 text-gray-600 hover:bg-gray-50",
                              )}
                            >
                              {humanise(c)}
                            </button>
                          );
                        })}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">None ticked means every kind of payment needs quotes.</p>
                    </>
                  ) : null}
                </div>
                <div className="mt-6 border-t border-gray-100 pt-5">
                  <p className="text-sm font-medium text-gray-900">Do your staff charge their time to donor projects?</p>
                  <p className="mb-3 text-xs text-gray-500">
                    Most donors want salaries charged by the time actually worked on their project. You can change this later in Settings.
                  </p>
                  <div className="space-y-2">
                    <Choice checked={a.staff_time === true} onChange={() => set("staff_time", true)}
                            title="Yes — staff record their time"
                            text="Staff tap what they worked on each day; supervisors sign; each grant is charged for the hours worked." />
                    <Choice checked={a.staff_time === false} onChange={() => set("staff_time", false)}
                            title="No"
                            text="Salaries are charged by each person's fixed split. No timesheets." />
                  </div>
                </div>
              </Section>
            )}

            {step === 6 && (
              <Section q="Check your setup" help="This is how requests will move once you save.">
                {!preview ? (
                  <p className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Working it out…</p>
                ) : (
                  <>
                    <ul className="space-y-3">
                      {preview.route.map((band) => (
                        <li key={band.span} className="rounded-xl border border-gray-200 p-3.5">
                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{band.span}</p>
                          <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-sm text-gray-900">
                            <span className="rounded-md bg-gray-100 px-2 py-0.5">Raised</span>
                            {band.steps.map((s) => (
                              <span key={s.label} className="inline-flex items-center gap-1.5">
                                <ArrowRight className="h-3.5 w-3.5 text-gray-400" />
                                <span className="rounded-md bg-brand-50 px-2 py-0.5 text-brand-800">{s.who}</span>
                              </span>
                            ))}
                            <ArrowRight className="h-3.5 w-3.5 text-gray-400" />
                            <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-emerald-800">Paid</span>
                          </p>
                          {band.steps.some((s) => s.may_release) ? (
                            <p className="mt-1.5 text-xs text-gray-500">
                              {band.steps.filter((s) => s.may_release).map((s) =>
                                `${s.who} may release a failing check with a written reason${s.release_limit ? ` up to ${money(s.release_limit, cur)}` : ""}.`,
                              ).join(" ")}
                            </p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                    {preview.documents.length ? (
                      <div>
                        <p className="text-sm font-medium text-gray-900">Paperwork</p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-gray-700">
                          {preview.documents.map((d) => <li key={d}>{d}</li>)}
                        </ul>
                      </div>
                    ) : null}
                    {preview.errors.length ? (
                      <div className="rounded-lg border border-red-200 bg-red-50 p-3.5 text-sm text-red-800">
                        <p className="font-semibold">Fix these before saving:</p>
                        <ul className="mt-1 list-disc pl-5">{preview.errors.map((e) => <li key={e}>{e}</li>)}</ul>
                      </div>
                    ) : null}
                    {preview.warnings.length ? (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-900">
                        <ul className="list-disc pl-5">{preview.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                      </div>
                    ) : null}
                    {saveError ? <p className="text-sm text-red-700">{saveError}</p> : null}
                    {saved ? (
                      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-900">
                        Saved. New requests follow this route from now on.{" "}
                        <Link href="/settings/users" className="font-semibold underline">Add your people next</Link>
                        {" "}— give each manager the approver role in their department.
                      </div>
                    ) : null}
                    <button
                      type="button"
                      onClick={save}
                      disabled={saving || !preview.ok}
                      className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      Save this setup
                    </button>
                  </>
                )}
              </Section>
            )}

            <div className="mt-6 flex items-center justify-between border-t border-gray-100 pt-4">
              <button type="button" disabled={step === 0} onClick={() => setStep(step - 1)} className={cn(ghostBtn, "disabled:opacity-40")}>
                <ArrowLeft className="h-4 w-4" /> Back
              </button>
              {step < STEPS.length - 1 ? (
                <button
                  type="button"
                  onClick={() => setStep(step + 1)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  Next <ArrowRight className="h-4 w-4" />
                </button>
              ) : null}
            </div>
          </div>
        )}
      </Page>
    </AppShell>
  );
}

const inputCls =
  "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";
const ghostBtn =
  "inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50";

function Section({ q, help, children }: { q: string; help: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{q}</h2>
        <p className="mt-1 text-sm text-gray-600">{help}</p>
      </div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-[10rem] flex-1">
      <span className="mb-1 block text-xs font-medium text-gray-700">{label}</span>
      {children}
    </label>
  );
}

function Choice({
  checked, onChange, title, text, children,
}: { checked: boolean; onChange: () => void; title: string; text: string; children?: React.ReactNode }) {
  return (
    <label className={cn("block cursor-pointer rounded-xl border p-3.5", checked ? "border-brand-400 bg-brand-50/50" : "border-gray-200 hover:bg-gray-50")}>
      <span className="flex items-start gap-3">
        <input type="radio" checked={checked} onChange={onChange} className="mt-1 h-4 w-4 text-brand-600" />
        <span>
          <span className="block text-sm font-medium text-gray-900">{title}</span>
          <span className="block text-sm text-gray-600">{text}</span>
        </span>
      </span>
      {children}
    </label>
  );
}

function Release({
  can, limit, currency, onCan, onLimit,
}: { can: boolean; limit: number | null; currency: string; onCan: (v: boolean) => void; onLimit: (v: number | null) => void }) {
  return (
    <div className="mt-3 rounded-lg bg-gray-50 p-3">
      <label className="flex items-start gap-2 text-sm text-gray-800">
        <input type="checkbox" checked={can} onChange={(e) => onCan(e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600" />
        <span>
          May approve a request that fails a check (say, a missing invoice), with a written reason that auditors can read
        </span>
      </label>
      {can ? (
        <div className="mt-2 max-w-xs">
          <Field label={`Up to (${currency}) — blank for no limit`}>
            <input
              className={inputCls}
              inputMode="numeric"
              value={limit ?? ""}
              onChange={(e) => onLimit(numOrNull(e.target.value))}
            />
          </Field>
        </div>
      ) : null}
    </div>
  );
}
