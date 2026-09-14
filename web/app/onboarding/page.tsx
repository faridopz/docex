"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  GitBranch,
  Loader2,
  Plus,
  Rocket,
  ShieldAlert,
  Sparkles,
  Trash2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { listDepartments, type DepartmentDef } from "@/lib/erpApi";
import { getWorkflow } from "@/lib/requisitionApi";
import {
  getOnboardingStatus,
  runOnboardingSetup,
  type DepartmentInput,
  type StepInput,
} from "@/lib/onboardingApi";

/**
 * /onboarding — the guided setup wizard.
 *
 * Replaces "ask a developer to hand-edit profiles/<client>.json" with an
 * admin answering a short sequence of questions inside the product. Five
 * screens, one call to action each (research on setup-wizard dropoff: 30-50%
 * abandon past five steps, and forcing every optional field up front is worse
 * than a working default the admin can revisit).
 *
 * Reachable two ways: automatically, via the banner AppShell shows an admin
 * when GET /onboarding/status says the org isn't configured yet; and anytime
 * after, as "Re-run setup" from Org Settings. Re-running PRE-FILLS from the
 * org's current departments + workflow, so fixing one threshold doesn't mean
 * re-answering five screens of unchanged answers.
 */

type Step = 0 | 1 | 2 | 3 | 4;

const PRESET_INFO: Record<string, string> = {
  small: "Submit → Finance. One step — for a small team where finance signs off directly.",
  medium: "Submit → Compliance → Finance → Management (above a threshold). A balanced default.",
  large: "Submit → Department Head → Compliance → Finance → Management. For larger, multi-department orgs.",
};

export default function OnboardingPage() {
  const router = useRouter();
  const { ready, user } = useAuth();

  const [step, setStep] = useState<Step>(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; partial: boolean; error: string | null } | null>(null);

  // Screen 1: basics
  const [currency, setCurrency] = useState("NGN");

  // Screen 2: departments
  const [depts, setDepts] = useState<DepartmentInput[]>([
    { name: "Program", is_final_authority: false },
    { name: "Finance", is_final_authority: false },
    { name: "Management", is_final_authority: true },
  ]);

  // Screen 3: approval chain
  const [workflowSize, setWorkflowSize] = useState<"small" | "medium" | "large" | "custom">("medium");
  const [customSteps, setCustomSteps] = useState<StepInput[]>([]);

  // Screen 4: spend policy
  const [maxAmount, setMaxAmount] = useState<string>("");
  const [categoriesText, setCategoriesText] = useState("");
  const [docsText, setDocsText] = useState("");

  // This page returns before ever rendering <AppShell>, so AppShell's own
  // "signed out -> /login" redirect never gets a chance to run for a visitor
  // who lands here without a session (a stale tab, a bookmark, a session that
  // expired). Without this, they'd sit on the loading spinner forever instead
  // of being bounced to sign in. Same reasoning for a signed-in non-admin —
  // they're routed to the dashboard rather than shown a page they can't act on.
  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
    } else if (user.role !== "admin") {
      router.replace("/dashboard");
    }
  }, [ready, user, router]);

  // Pre-fill from whatever already exists, so re-running setup doesn't force
  // re-answering questions the admin already answered once.
  useEffect(() => {
    if (!ready || !user || user.role !== "admin") return;
    (async () => {
      try {
        const status = await getOnboardingStatus();
        if (status.departments_configured) {
          const { departments } = await listDepartments();
          if (departments.length) {
            setDepts(departments.map((d) => ({
              name: d.name, key: d.key, is_final_authority: d.is_final_authority,
            })));
          }
        }
        if (status.workflow_configured) {
          const wf = await getWorkflow();
          setCurrency(wf.currency || "NGN");
          setMaxAmount(wf.max_amount != null ? String(wf.max_amount) : "");
          setCategoriesText(wf.allowed_categories.join(", "));
          setDocsText(wf.required_documents.join(", "));
          if (wf.steps.length) {
            setWorkflowSize("custom");
            setCustomSteps(wf.steps.map((s) => ({
              label: s.label, department: s.department,
              min_amount: s.min_amount, can_override: s.can_override,
              override_limit: s.override_limit,
            })));
          }
        }
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Could not load current setup.");
      } finally {
        setLoading(false);
      }
    })();
  }, [ready, user]);

  if (!ready || !user || user.role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#fafaf7] text-sm text-gray-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  const steps = ["Organisation", "Departments", "Approval chain", "Spend policy", "Review"];

  function addDept() {
    setDepts([...depts, { name: "", is_final_authority: false }]);
  }
  function updateDept(i: number, patch: Partial<DepartmentInput>) {
    setDepts(depts.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }
  function removeDept(i: number) {
    setDepts(depts.filter((_, idx) => idx !== i));
  }

  function addCustomStep() {
    setCustomSteps([...customSteps, {
      label: "", department: depts[0]?.key || depts[0]?.name?.toLowerCase() || "",
      min_amount: 0, can_override: false, override_limit: null,
    }]);
  }
  function updateCustomStep(i: number, patch: Partial<StepInput>) {
    setCustomSteps(customSteps.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
  function removeCustomStep(i: number) {
    setCustomSteps(customSteps.filter((_, idx) => idx !== i));
  }

  function canAdvance(): boolean {
    if (step === 1) return depts.length > 0 && depts.every((d) => d.name.trim());
    if (step === 2) return workflowSize !== "custom" || customSteps.length > 0;
    return true;
  }

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitError(null);
    setResult(null);
    try {
      const res = await runOnboardingSetup({
        currency: currency.trim().toUpperCase() || "NGN",
        departments: depts.map((d) => ({
          name: d.name.trim(),
          key: d.key,
          is_final_authority: !!d.is_final_authority,
        })),
        workflow_size: workflowSize,
        custom_steps: workflowSize === "custom" ? customSteps : undefined,
        max_amount: maxAmount.trim() ? Number(maxAmount) : null,
        allowed_categories: categoriesText.split(",").map((s) => s.trim()).filter(Boolean),
        required_documents: docsText.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setResult(res);
      if (res.ok) {
        setTimeout(() => router.push("/dashboard"), 1200);
      }
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Setup failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell active="dashboard">
      <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="mb-6 flex items-center gap-2">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            <Sparkles className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">Set up your organisation</h1>
            <p className="text-xs text-gray-500">
              Five short steps — departments and your approval chain. You can change any of this later in Org Settings.
            </p>
          </div>
        </div>

        {/* Progress */}
        <div className="mb-6 flex items-center gap-1.5">
          {steps.map((label, i) => (
            <div key={label} className="flex flex-1 items-center gap-1.5">
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                  i < step ? "bg-brand-600 text-white"
                    : i === step ? "bg-brand-100 text-brand-700 ring-2 ring-brand-300"
                    : "bg-gray-100 text-gray-400",
                )}
              >
                {i < step ? <Check className="h-3 w-3" /> : i + 1}
              </div>
              {i < steps.length - 1 && <div className={cn("h-0.5 flex-1", i < step ? "bg-brand-600" : "bg-gray-100")} />}
            </div>
          ))}
        </div>
        <p className="mb-5 text-xs font-medium uppercase tracking-wide text-gray-400">{steps[step]}</p>

        {loading ? (
          <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white p-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading your current setup…
          </div>
        ) : (
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            {loadError && (
              <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                {loadError} — starting from defaults instead.
              </p>
            )}

            {step === 0 && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                  <Building2 className="h-4 w-4 text-gray-400" /> Currency
                </div>
                <p className="text-xs text-gray-500">Every amount in the system — thresholds, requisitions, payments — is shown in this currency.</p>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className={inputCls}
                >
                  <option value="NGN">NGN — Nigerian Naira</option>
                  <option value="USD">USD — US Dollar</option>
                  <option value="GBP">GBP — British Pound</option>
                  <option value="EUR">EUR — Euro</option>
                  <option value="KES">KES — Kenyan Shilling</option>
                  <option value="GHS">GHS — Ghanaian Cedi</option>
                </select>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                    <Building2 className="h-4 w-4 text-gray-400" /> Departments
                  </div>
                  <button type="button" onClick={addDept} className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
                    <Plus className="h-3.5 w-3.5" /> Add
                  </button>
                </div>
                <p className="text-xs text-gray-500">Who's involved in raising or approving a payment? Mark the one that gives final authorisation.</p>
                <div className="space-y-2">
                  {depts.map((d, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        value={d.name}
                        onChange={(e) => updateDept(i, { name: e.target.value })}
                        placeholder="Department name"
                        className={cn(inputCls, "flex-1")}
                      />
                      <label className="flex shrink-0 items-center gap-1.5 text-xs text-gray-600">
                        <input
                          type="checkbox"
                          checked={!!d.is_final_authority}
                          onChange={(e) => updateDept(i, { is_final_authority: e.target.checked })}
                        />
                        Final authority
                      </label>
                      <button type="button" onClick={() => removeDept(i)} className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                  <GitBranch className="h-4 w-4 text-gray-400" /> Approval chain
                </div>
                <div className="space-y-2">
                  {(["small", "medium", "large", "custom"] as const).map((size) => (
                    <label
                      key={size}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm transition",
                        workflowSize === size ? "border-brand-400 bg-brand-50/60" : "border-gray-200 hover:bg-gray-50",
                      )}
                    >
                      <input
                        type="radio"
                        name="wf-size"
                        checked={workflowSize === size}
                        onChange={() => setWorkflowSize(size)}
                        className="mt-0.5"
                      />
                      <div>
                        <p className="font-medium capitalize text-gray-900">{size}</p>
                        <p className="text-xs text-gray-500">
                          {size === "custom" ? "Build your own chain, step by step." : PRESET_INFO[size]}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>

                {workflowSize === "custom" && (
                  <div className="space-y-2 rounded-lg border border-dashed border-gray-300 p-3">
                    {customSteps.map((s, i) => (
                      <div key={i} className="flex flex-wrap items-center gap-2">
                        <input
                          value={s.label}
                          onChange={(e) => updateCustomStep(i, { label: e.target.value })}
                          placeholder="Step label, e.g. Compliance Review"
                          className={cn(inputCls, "w-48")}
                        />
                        <select
                          value={s.department}
                          onChange={(e) => updateCustomStep(i, { department: e.target.value })}
                          className={cn(inputCls, "w-40")}
                        >
                          {depts.map((d) => (
                            <option key={d.name} value={d.key || d.name.toLowerCase().replace(/\s+/g, "-")}>{d.name}</option>
                          ))}
                        </select>
                        <input
                          type="number"
                          value={s.min_amount ?? 0}
                          onChange={(e) => updateCustomStep(i, { min_amount: Number(e.target.value) })}
                          placeholder="Min amount"
                          className={cn(inputCls, "w-32")}
                        />
                        <button type="button" onClick={() => removeCustomStep(i)} className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addCustomStep} className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50">
                      <Plus className="h-3.5 w-3.5" /> Add step
                    </button>
                  </div>
                )}
              </div>
            )}

            {step === 3 && (
              <div className="space-y-4">
                <div className="text-sm font-medium text-gray-900">Spend policy (optional)</div>
                <p className="text-xs text-gray-500">Leave any of these blank — they can be set later in Org Settings, and nothing here blocks setup.</p>
                <Field label={`Per-requisition ceiling (${currency})`}>
                  <input
                    type="number"
                    value={maxAmount}
                    onChange={(e) => setMaxAmount(e.target.value)}
                    placeholder="No ceiling"
                    className={inputCls}
                  />
                </Field>
                <Field label="Allowed spend categories (comma-separated)">
                  <input
                    value={categoriesText}
                    onChange={(e) => setCategoriesText(e.target.value)}
                    placeholder="e.g. travel, supplies, training"
                    className={inputCls}
                  />
                </Field>
                <Field label="Documents required on every requisition (comma-separated)">
                  <input
                    value={docsText}
                    onChange={(e) => setDocsText(e.target.value)}
                    placeholder="e.g. receipt, invoice"
                    className={inputCls}
                  />
                </Field>
              </div>
            )}

            {step === 4 && (
              <div className="space-y-4">
                <div className="text-sm font-medium text-gray-900">Review</div>
                <SummaryRow label="Currency" value={currency} />
                <SummaryRow label="Departments" value={depts.map((d) => d.name).filter(Boolean).join(", ") || "—"} />
                <SummaryRow label="Approval chain" value={workflowSize === "custom" ? `Custom (${customSteps.length} steps)` : `${workflowSize[0].toUpperCase()}${workflowSize.slice(1)} preset`} />
                <SummaryRow label="Ceiling" value={maxAmount ? `${currency} ${maxAmount}` : "None"} />
                <SummaryRow label="Categories" value={categoriesText || "All allowed"} />
                <SummaryRow label="Required documents" value={docsText || "None"} />

                {submitError && (
                  <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                    <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {submitError}
                  </p>
                )}
                {result && !result.ok && (
                  <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                    <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {result.partial
                      ? `Departments saved, but the approval chain was rejected: ${result.error}`
                      : result.error}
                  </p>
                )}
                {result?.ok && (
                  <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
                    <Check className="h-3.5 w-3.5" /> Setup complete — taking you to the dashboard…
                  </p>
                )}
              </div>
            )}

            {/* Nav */}
            <div className="mt-6 flex items-center justify-between border-t border-gray-100 pt-4">
              <button
                type="button"
                onClick={() => setStep((s) => (s > 0 ? ((s - 1) as Step) : s))}
                disabled={step === 0 || submitting}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 disabled:opacity-40"
              >
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </button>

              {step < 4 ? (
                <button
                  type="button"
                  onClick={() => setStep((s) => ((s + 1) as Step))}
                  disabled={!canAdvance()}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
                >
                  Next <ArrowRight className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={submitting || (result?.ok ?? false)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60"
                >
                  {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
                  Apply setup
                </button>
              )}
            </div>
          </div>
        )}

        <p className="mt-4 text-center text-[11px] text-gray-400">
          Not ready? <Link href="/dashboard" className="text-brand-600">Skip for now</Link> — you can run this again anytime from Org Settings.
        </p>
      </div>
    </AppShell>
  );
}

const inputCls =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-gray-50 py-1.5 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="text-right font-medium text-gray-900">{value}</span>
    </div>
  );
}
