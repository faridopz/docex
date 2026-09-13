"use client";

import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Building2,
  Check,
  GitBranch,
  Loader2,
  Plus,
  Shield,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { GuidanceCard } from "@/components/GuidanceCard";
import { getOrgProfile, updateOrgProfile } from "@/lib/api";
import { listDepartments, type DepartmentDef } from "@/lib/erpApi";
import { getWorkflow, setWorkflow } from "@/lib/requisitionApi";
import {
  getClientConfig,
  setClientConfig,
  ALL_MODULES,
  ALL_FEATURES,
  type ClientConfig,
} from "@/lib/orgConfig";
import type { RequisitionWorkflow, WorkflowStep } from "@/types/requisition";
import type { OrgProfile, PaymentType } from "@/types";

/**
 * Organisation settings.
 *
 * This page edits TWO separate configuration surfaces, on purpose kept
 * visibly separate rather than papered over as one:
 *
 *   1. The approval workflow + modules/features — what the requisition
 *      engine actually runs payments on, and what nav a user sees at all.
 *      Store-backed, org-scoped, survives redeploy, validated before write
 *      (a step can't route to a department that doesn't exist, an
 *      override_limit can't sit below the min_amount it's meant to cover).
 *      This is "flexible, based on your own system."
 *   2. Organisation name, payment types, and their document checklists —
 *      feeds the AI-assisted compliance-check flow (rulebooks). Older,
 *      still live, being folded into (1) over time.
 *
 * Departments themselves (add/rename/delete) are managed on Settings →
 * Departments & team, not duplicated here — the workflow editor below reads
 * that same list for its department dropdowns.
 */

type StageRow = { name: string; email: string };

export default function OrgSettingsPage() {
  // ── legacy org profile (name, payment subject, payment types, vendors) ──
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("Payment requisition");
  const [stages, setStages] = useState<StageRow[]>([]);
  const [types, setTypes] = useState<PaymentType[]>([]);
  const [approvedVendors, setApprovedVendors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // ── departments (read-only here; managed on Settings → Departments) ──
  const [departments, setDepartments] = useState<DepartmentDef[]>([]);

  // ── the real approval workflow (requisitions engine) ──
  const [workflow, setWf] = useState<RequisitionWorkflow | null>(null);
  const [wfSaving, setWfSaving] = useState(false);
  const [wfSaved, setWfSaved] = useState(false);
  const [wfError, setWfError] = useState<string | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [newCategoryDocs, setNewCategoryDocs] = useState("");

  // ── modules & features (real nav gating) ──
  const [cc, setCc] = useState<ClientConfig | null>(null);
  const [ccSaving, setCcSaving] = useState(false);
  const [ccSaved, setCcSaved] = useState(false);
  const [ccError, setCcError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, depts, wf, clientConfig] = await Promise.all([
          getOrgProfile(),
          listDepartments(),
          getWorkflow(),
          getClientConfig(),
        ]);
        if (cancelled) return;
        setName(p.name ?? "");
        setSubject(p.payment_subject ?? "Payment requisition");
        setStages(
          (p.default_approval_workflow ?? []).map((s) => ({
            name: s,
            email: p.directory?.[s] ?? "",
          })),
        );
        setTypes(p.payment_types ?? []);
        setApprovedVendors(p.approved_vendors ?? []);
        setDepartments(depts.departments ?? []);
        setWf(wf);
        setCc(clientConfig);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not load org settings.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── legacy profile handlers ──

  function patch(i: number, p: Partial<StageRow>) {
    setStages((s) => s.map((row, idx) => (idx === i ? { ...row, ...p } : row)));
    setSaved(false);
  }
  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= stages.length) return;
    const next = [...stages];
    [next[i], next[j]] = [next[j], next[i]];
    setStages(next);
    setSaved(false);
  }
  function remove(i: number) {
    setStages((s) => s.filter((_, idx) => idx !== i));
    setSaved(false);
  }
  function add() {
    setStages((s) => [...s, { name: "", email: "" }]);
    setSaved(false);
  }

  function patchType(i: number, p: Partial<PaymentType>) {
    setTypes((ts) => ts.map((t, idx) => (idx === i ? { ...t, ...p } : t)));
    setSaved(false);
  }
  function removeType(i: number) {
    setTypes((ts) => ts.filter((_, idx) => idx !== i));
    setSaved(false);
  }
  function addType() {
    setTypes((ts) => [
      ...ts,
      { name: "", required_documents: [], notes: "", intake_mode: "document", form_fields: [] },
    ]);
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const directory: Record<string, string> = {};
      for (const row of stages) {
        const n = row.name.trim();
        const e = row.email.trim();
        if (n && e) directory[n] = e;
      }
      const profile: OrgProfile = {
        name: name.trim() || "Your organisation",
        payment_subject: subject.trim() || "Payment requisition",
        enabled_modules: cc?.modules ?? ["compliance", "screening", "knowledge"],
        roles: [],
        approved_vendors: approvedVendors,
        default_approval_workflow: stages
          .map((s) => s.name.trim())
          .filter(Boolean),
        directory,
        payment_types: types
          .filter((t) => t.name.trim())
          .map((t) => ({
            name: t.name.trim(),
            required_documents: t.required_documents
              .map((d) => d.trim())
              .filter(Boolean),
            notes: (t.notes ?? "").trim() || null,
            intake_mode: t.intake_mode ?? "document",
            form_fields: t.form_fields ?? [],
            default_rulebook_id: t.default_rulebook_id ?? null,
          })),
      };
      const savedProfile = await updateOrgProfile(profile);
      setName(savedProfile.name);
      setSubject(savedProfile.payment_subject ?? "Payment requisition");
      setStages(
        (savedProfile.default_approval_workflow ?? []).map((s) => ({
          name: s,
          email: savedProfile.directory?.[s] ?? "",
        })),
      );
      setTypes(savedProfile.payment_types ?? []);
      setApprovedVendors(savedProfile.approved_vendors ?? []);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  // ── real workflow handlers ──

  function patchWf(p: Partial<RequisitionWorkflow>) {
    setWf((w) => (w ? { ...w, ...p } : w));
    setWfSaved(false);
  }
  function patchStep(i: number, p: Partial<WorkflowStep>) {
    setWf((w) => {
      if (!w) return w;
      const steps = [...w.steps];
      steps[i] = { ...steps[i], ...p };
      return { ...w, steps };
    });
    setWfSaved(false);
  }
  function moveStep(i: number, dir: -1 | 1) {
    setWf((w) => {
      if (!w) return w;
      const j = i + dir;
      if (j < 0 || j >= w.steps.length) return w;
      const steps = [...w.steps];
      [steps[i], steps[j]] = [steps[j], steps[i]];
      return { ...w, steps };
    });
    setWfSaved(false);
  }
  function removeStep(i: number) {
    setWf((w) => (w ? { ...w, steps: w.steps.filter((_, idx) => idx !== i) } : w));
    setWfSaved(false);
  }
  function addStep() {
    setWf((w) => {
      if (!w) return w;
      const n = w.steps.length + 1;
      return {
        ...w,
        steps: [
          ...w.steps,
          {
            key: `step-${n}-${Date.now().toString(36).slice(-4)}`,
            label: "",
            department: departments[0]?.key ?? "",
            min_amount: 0,
            can_override: false,
            override_limit: null,
          },
        ],
      };
    });
    setWfSaved(false);
  }

  function addCategoryPack() {
    const cat = newCategory.trim();
    if (!cat) return;
    setWf((w) =>
      w
        ? {
            ...w,
            documents_by_category: {
              ...w.documents_by_category,
              [cat]: newCategoryDocs.split(",").map((d) => d.trim()).filter(Boolean),
            },
          }
        : w,
    );
    setNewCategory("");
    setNewCategoryDocs("");
    setWfSaved(false);
  }
  function removeCategoryPack(cat: string) {
    setWf((w) => {
      if (!w) return w;
      const next = { ...w.documents_by_category };
      delete next[cat];
      return { ...w, documents_by_category: next };
    });
    setWfSaved(false);
  }
  function patchCategoryPack(cat: string, docsCsv: string) {
    setWf((w) =>
      w
        ? {
            ...w,
            documents_by_category: {
              ...w.documents_by_category,
              [cat]: docsCsv.split(",").map((d) => d.trim()).filter(Boolean),
            },
          }
        : w,
    );
    setWfSaved(false);
  }

  async function saveWorkflow() {
    if (!workflow) return;
    setWfSaving(true);
    setWfError(null);
    setWfSaved(false);
    try {
      const cleaned: RequisitionWorkflow = {
        ...workflow,
        steps: workflow.steps.map((s) => ({ ...s, key: s.key.trim() || s.label.trim().toLowerCase().replace(/\s+/g, "-") })),
        allowed_categories: workflow.allowed_categories.map((c) => c.trim()).filter(Boolean),
        required_documents: workflow.required_documents.map((d) => d.trim()).filter(Boolean),
      };
      const savedWf = await setWorkflow(cleaned);
      setWf(savedWf);
      setWfSaved(true);
    } catch (err) {
      // The backend names exactly which step/department/limit is wrong —
      // surface that verbatim rather than a generic "could not save."
      setWfError(err instanceof Error ? err.message : "Could not save the workflow.");
    } finally {
      setWfSaving(false);
    }
  }

  // ── modules & features handlers ──

  function toggleCcModule(key: string) {
    setCc((c) =>
      c
        ? {
            ...c,
            modules: (c.modules.includes(key as never)
              ? c.modules.filter((m) => m !== key)
              : [...c.modules, key]) as ClientConfig["modules"],
          }
        : c,
    );
    setCcSaved(false);
  }
  function toggleCcFeature(key: string) {
    setCc((c) =>
      c ? { ...c, features: { ...c.features, [key]: !c.features[key] } } : c,
    );
    setCcSaved(false);
  }
  async function saveClientConfig() {
    if (!cc) return;
    setCcSaving(true);
    setCcError(null);
    setCcSaved(false);
    try {
      const savedCc = await setClientConfig({ modules: cc.modules, features: cc.features });
      setCc(savedCc);
      setCcSaved(true);
    } catch (err) {
      setCcError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setCcSaving(false);
    }
  }

  return (
    <AppShell active="compliance">
      <main className="mx-auto max-w-2xl px-6 py-10">
        <div className="mb-8 flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Building2 className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">
              Organisation settings
            </h1>
            <p className="text-sm text-gray-600">
              Configure how DOCex works for your organisation.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="space-y-10">
            {/* ══════════ Modules & features — real nav gating ══════════ */}
            <section className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="flex items-start gap-3">
                <Shield className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div className="flex-1 space-y-1">
                  <h3 className="text-base font-semibold text-gray-900">
                    Modules &amp; features
                  </h3>
                  <p className="text-sm text-gray-600">
                    What this organisation can see. One engine underneath —
                    switch on only what you use.
                  </p>
                </div>
              </div>

              {!cc ? null : (
                <>
                  <div className="mt-5 space-y-2">
                    {ALL_MODULES.map((m) => {
                      const on = cc.modules.includes(m.key);
                      return (
                        <button
                          key={m.key}
                          type="button"
                          onClick={() => toggleCcModule(m.key)}
                          className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition ${
                            on
                              ? "border-brand-300 bg-brand-50/50"
                              : "border-gray-200 bg-white hover:border-gray-300"
                          }`}
                        >
                          <ToggleDot on={on} />
                          <span className="min-w-0">
                            <span className="block text-sm font-semibold text-gray-900">
                              {m.label}
                            </span>
                            <span className="block text-xs text-gray-500">{m.desc}</span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  {cc.modules.length === 0 && (
                    <p className="mt-2 text-xs text-amber-700">
                      At least one module stays on — an org with none would see an
                      empty app.
                    </p>
                  )}

                  <div className="mt-5 border-t border-gray-100 pt-4">
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      Features within Compliance &amp; Finance
                    </h4>
                    <div className="space-y-2">
                      {ALL_FEATURES.map((f) => {
                        const on = cc.features[f.key] === true;
                        return (
                          <button
                            key={f.key}
                            type="button"
                            onClick={() => toggleCcFeature(f.key)}
                            className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition ${
                              on
                                ? "border-brand-300 bg-brand-50/50"
                                : "border-gray-200 bg-white hover:border-gray-300"
                            }`}
                          >
                            <ToggleDot on={on} />
                            <span className="min-w-0">
                              <span className="block text-sm font-semibold text-gray-900">
                                {f.label}
                              </span>
                              <span className="block text-xs text-gray-500">{f.desc}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {ccError && (
                    <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                      {ccError}
                    </p>
                  )}
                  <div className="mt-4 flex items-center gap-3">
                    <button
                      type="button"
                      onClick={saveClientConfig}
                      disabled={ccSaving}
                      className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {ccSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      Save modules &amp; features
                    </button>
                    {ccSaved && (
                      <span className="text-sm font-medium text-emerald-600">Saved ✓</span>
                    )}
                  </div>
                </>
              )}
            </section>

            {/* ══════════ Approval workflow — the real engine ══════════ */}
            <section className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="flex items-start gap-3">
                <GitBranch className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div className="flex-1 space-y-1">
                  <h3 className="text-base font-semibold text-gray-900">
                    Approval workflow
                  </h3>
                  <p className="text-sm text-gray-600">
                    What every requisition actually runs on: the sign-off
                    chain, spend thresholds, and who may release a blocked
                    payment. Steps route to your{" "}
                    <Link href="/settings/departments" className="text-brand-600 underline">
                      departments
                    </Link>
                    — add a department there first if it's missing below.
                  </p>
                </div>
                <Link
                  href="/onboarding"
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50"
                >
                  <Sparkles className="h-3.5 w-3.5" /> Re-run setup wizard
                </Link>
              </div>

              {!workflow ? null : (
                <>
                  <div className="mt-5 space-y-2">
                    {workflow.steps.length === 0 && (
                      <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-4 text-center text-xs text-gray-500">
                        No steps yet — every requisition would have nothing to
                        wait on. Add the first step of your approval chain.
                      </p>
                    )}
                    {workflow.steps.map((s, i) => (
                      <div
                        key={i}
                        className="space-y-2 rounded-lg border border-gray-100 bg-gray-50/50 p-3"
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                            {i + 1}
                          </span>
                          <input
                            type="text"
                            value={s.label}
                            onChange={(e) => patchStep(i, { label: e.target.value })}
                            placeholder='Step label — e.g. "Finance Review"'
                            className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                          />
                          <select
                            value={s.department}
                            onChange={(e) => patchStep(i, { department: e.target.value })}
                            className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                          >
                            <option value="">Select department…</option>
                            {departments.map((d) => (
                              <option key={d.key} value={d.key}>
                                {d.name}
                              </option>
                            ))}
                          </select>
                          <div className="flex shrink-0 items-center gap-0.5">
                            <button type="button" onClick={() => moveStep(i, -1)} disabled={i === 0}
                              className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30" aria-label="Move up">
                              <ArrowUp className="h-3.5 w-3.5" />
                            </button>
                            <button type="button" onClick={() => moveStep(i, 1)} disabled={i === workflow.steps.length - 1}
                              className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30" aria-label="Move down">
                              <ArrowDown className="h-3.5 w-3.5" />
                            </button>
                            <button type="button" onClick={() => removeStep(i)}
                              className="rounded-md p-1.5 text-gray-300 transition hover:bg-rose-50 hover:text-rose-600" aria-label="Remove step">
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 pl-8 text-xs text-gray-600">
                          <label className="flex items-center gap-1.5">
                            Engages at
                            <input
                              type="number"
                              value={s.min_amount}
                              onChange={(e) => patchStep(i, { min_amount: Number(e.target.value) || 0 })}
                              className="w-28 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs"
                            />
                            {workflow.currency} and above
                          </label>
                          <label className="flex items-center gap-1.5">
                            <input
                              type="checkbox"
                              checked={s.can_override}
                              onChange={(e) => patchStep(i, {
                                can_override: e.target.checked,
                                override_limit: e.target.checked ? (s.override_limit ?? s.min_amount) : null,
                              })}
                              className="h-3.5 w-3.5 rounded border-gray-300"
                            />
                            Can override a blocked check
                          </label>
                          {s.can_override && (
                            <label className="flex items-center gap-1.5">
                              up to
                              <input
                                type="number"
                                value={s.override_limit ?? 0}
                                onChange={(e) => patchStep(i, { override_limit: Number(e.target.value) || 0 })}
                                className="w-28 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs"
                              />
                              {workflow.currency}
                            </label>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <button type="button" onClick={addStep}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700">
                    <Plus className="h-4 w-4" /> Add step
                  </button>

                  {/* Spend policy */}
                  <div className="mt-6 grid gap-3 border-t border-gray-100 pt-5 sm:grid-cols-2">
                    <label className="space-y-1 text-sm">
                      <span className="font-medium text-gray-900">Per-requisition ceiling</span>
                      <input
                        type="number"
                        value={workflow.max_amount ?? ""}
                        placeholder="No ceiling"
                        onChange={(e) => patchWf({ max_amount: e.target.value === "" ? null : Number(e.target.value) })}
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                      />
                    </label>
                    <label className="space-y-1 text-sm">
                      <span className="font-medium text-gray-900">Currency</span>
                      <input
                        type="text"
                        value={workflow.currency}
                        onChange={(e) => patchWf({ currency: e.target.value.toUpperCase().slice(0, 3) })}
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                      />
                    </label>
                    <label className="space-y-1 text-sm sm:col-span-2">
                      <span className="font-medium text-gray-900">Allowed spend categories</span>
                      <input
                        type="text"
                        value={workflow.allowed_categories.join(", ")}
                        placeholder="Any category — leave blank to allow all"
                        onChange={(e) => patchWf({ allowed_categories: e.target.value.split(",") })}
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                      />
                    </label>
                    <label className="space-y-1 text-sm sm:col-span-2">
                      <span className="font-medium text-gray-900">Documents required on every requisition</span>
                      <input
                        type="text"
                        value={workflow.required_documents.join(", ")}
                        placeholder="e.g. memo, invoice"
                        onChange={(e) => patchWf({ required_documents: e.target.value.split(",") })}
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
                      />
                      <span className="block text-xs text-gray-500">
                        The fallback list — a category below with its own pack uses that instead.
                      </span>
                    </label>
                  </div>

                  {/* Per-category document packs */}
                  <div className="mt-6 border-t border-gray-100 pt-5">
                    <h4 className="text-sm font-semibold text-gray-900">Per-category document packs</h4>
                    <p className="mt-0.5 text-xs text-gray-500">
                      A goods purchase needs a GRN; a travel advance doesn't. One flat
                      checklist for every category trains people to ignore it.
                    </p>
                    <div className="mt-3 space-y-2">
                      {Object.entries(workflow.documents_by_category).map(([cat, docs]) => (
                        <div key={cat} className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50/50 p-2.5">
                          <span className="w-32 shrink-0 truncate text-sm font-medium text-gray-800">{cat}</span>
                          <input
                            type="text"
                            value={docs.join(", ")}
                            onChange={(e) => patchCategoryPack(cat, e.target.value)}
                            className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm"
                          />
                          <button type="button" onClick={() => removeCategoryPack(cat)}
                            className="shrink-0 rounded-md p-1.5 text-gray-300 transition hover:bg-rose-50 hover:text-rose-600" aria-label="Remove pack">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="text"
                        value={newCategory}
                        onChange={(e) => setNewCategory(e.target.value)}
                        placeholder="Category — e.g. equipment"
                        className="w-32 shrink-0 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm"
                      />
                      <input
                        type="text"
                        value={newCategoryDocs}
                        onChange={(e) => setNewCategoryDocs(e.target.value)}
                        placeholder="Required docs, comma-separated"
                        className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm"
                      />
                      <button type="button" onClick={addCategoryPack}
                        className="shrink-0 inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:border-brand-300 hover:text-brand-700">
                        <Plus className="h-3.5 w-3.5" /> Add
                      </button>
                    </div>
                  </div>

                  {wfError && (
                    <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                      {wfError}
                    </p>
                  )}
                  <div className="mt-5 flex items-center gap-3 border-t border-gray-100 pt-5">
                    <button
                      type="button"
                      onClick={saveWorkflow}
                      disabled={wfSaving}
                      className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {wfSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                      Save workflow
                    </button>
                    {wfSaved && (
                      <span className="text-sm font-medium text-emerald-600">Saved ✓</span>
                    )}
                  </div>
                </>
              )}
            </section>

            <GuidanceCard title="One engine, any organisation">
              The workflow above is what actually runs payments — it's
              validated before it saves, so a step can never route to a
              department that doesn't exist, and an override limit can never
              sit below the amount it's meant to cover.
            </GuidanceCard>

            {/* ══════════ Legacy: org name, payment subject, doc checklists for AI checks ══════════ */}
            <section className="space-y-8 border-t border-gray-200 pt-8">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Organisation profile &amp; compliance-check document lists
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Your name, what you call a payment request, and the document
                  checklists the AI-assisted compliance check uses. Separate
                  from the approval workflow above.
                </p>
              </div>

              <section className="space-y-2">
                <label className="block text-sm font-semibold text-gray-900">
                  Organisation name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                  placeholder="e.g. TA Connect"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </section>

              <section className="space-y-2">
                <label className="block text-sm font-semibold text-gray-900">
                  What you call a payment request
                </label>
                <p className="text-xs text-gray-500">
                  The artifact an officer checks at intake. Staff submit a{" "}
                  <span className="font-medium">requisition</span>; Finance later
                  turns an approved one into a <span className="font-medium">voucher (PV)</span>.
                  Use whichever term your team uses.
                </p>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => {
                    setSubject(e.target.value);
                    setSaved(false);
                  }}
                  placeholder="e.g. Payment requisition"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </section>

              {/* Default approval workflow + routing (legacy — drives rulebook sign-off inheritance) */}
              <section className="rounded-xl border border-gray-200 bg-white p-5">
                <div className="flex items-start gap-3">
                  <GitBranch className="mt-0.5 h-5 w-5 shrink-0 text-gray-400" />
                  <div className="flex-1 space-y-1">
                    <h3 className="text-base font-semibold text-gray-900">
                      Rulebook sign-off chain
                    </h3>
                    <p className="text-sm text-gray-600">
                      New AI-interpreted rulebooks inherit this chain. Add a
                      person per stage and sign-off requests route to them by
                      email.
                    </p>
                  </div>
                </div>

                <div className="mt-5 space-y-2">
                  {stages.length === 0 && (
                    <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-4 text-center text-xs text-gray-500">
                      No stages yet — add the first stage of your sign-off chain.
                    </p>
                  )}
                  {stages.map((row, i) => (
                    <div
                      key={i}
                      className="flex flex-col gap-2 rounded-lg border border-gray-100 bg-gray-50/50 p-3 sm:flex-row sm:items-center"
                    >
                      <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                        {i + 1}
                      </span>
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) => patch(i, { name: e.target.value })}
                        placeholder='Stage — e.g. "Compliance Check"'
                        className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                      <input
                        type="email"
                        value={row.email}
                        onChange={(e) => patch(i, { email: e.target.value })}
                        placeholder="approver@org.com (optional)"
                        className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                      <div className="flex shrink-0 items-center gap-0.5">
                        <button
                          type="button"
                          onClick={() => move(i, -1)}
                          disabled={i === 0}
                          className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30"
                          aria-label="Move up"
                        >
                          <ArrowUp className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => move(i, 1)}
                          disabled={i === stages.length - 1}
                          className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-30"
                          aria-label="Move down"
                        >
                          <ArrowDown className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => remove(i)}
                          className="rounded-md p-1.5 text-gray-300 transition hover:bg-rose-50 hover:text-rose-600"
                          aria-label="Remove stage"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={add}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
                >
                  <Plus className="h-4 w-4" />
                  Add stage
                </button>
              </section>

              {/* Payment types + required-doc checklists (legacy — compliance/check/form) */}
              <section className="rounded-xl border border-gray-200 bg-white p-5">
                <div className="flex items-start gap-3">
                  <Building2 className="mt-0.5 h-5 w-5 shrink-0 text-gray-400" />
                  <div className="flex-1 space-y-1">
                    <h3 className="text-base font-semibold text-gray-900">
                      Payment types &amp; required documents
                    </h3>
                    <p className="text-sm text-gray-600">
                      Each payment type carries its own document checklist for
                      the AI-assisted compliance check. Officers pick a type
                      when checking a payment.
                    </p>
                  </div>
                </div>

                <div className="mt-5 space-y-3">
                  {types.map((t, i) => (
                    <div
                      key={i}
                      className="space-y-2 rounded-xl border border-gray-100 bg-gray-50/50 p-3"
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={t.name}
                          onChange={(e) => patchType(i, { name: e.target.value })}
                          placeholder="Type name — e.g. Procurement Payment"
                          className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                        />
                        <button
                          type="button"
                          onClick={() => removeType(i)}
                          className="rounded-md p-1.5 text-gray-300 transition hover:bg-rose-50 hover:text-rose-600"
                          aria-label="Remove type"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <input
                        type="text"
                        value={t.required_documents.join(", ")}
                        onChange={(e) =>
                          patchType(i, {
                            required_documents: e.target.value.split(","),
                          })
                        }
                        placeholder="Required documents, comma-separated — e.g. PO, Invoice, GRN"
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                      <input
                        type="text"
                        value={t.notes ?? ""}
                        onChange={(e) => patchType(i, { notes: e.target.value })}
                        placeholder="Special rule (optional) — e.g. retire within 5 working days"
                        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                      />
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={addType}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
                >
                  <Plus className="h-4 w-4" />
                  Add payment type
                </button>
              </section>

              {error && (
                <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </p>
              )}

              <div className="flex items-center gap-3 border-t border-gray-200 pt-6">
                <button
                  type="button"
                  onClick={save}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  Save profile
                </button>
                {saved && (
                  <span className="text-sm font-medium text-emerald-600">
                    Saved ✓
                  </span>
                )}
              </div>
            </section>
          </div>
        )}
      </main>
    </AppShell>
  );
}

function ToggleDot({ on }: { on: boolean }) {
  return (
    <span
      className={`mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full transition ${
        on ? "bg-brand-600" : "bg-gray-200"
      }`}
    >
      <span
        className={`h-4 w-4 transform rounded-full bg-white shadow transition ${
          on ? "translate-x-[18px]" : "translate-x-0.5"
        }`}
      />
    </span>
  );
}
