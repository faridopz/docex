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
  Trash2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { GuidanceCard } from "@/components/GuidanceCard";
import { getOrgProfile, updateOrgProfile } from "@/lib/api";
import type { OrgProfile, PaymentType } from "@/types";

/**
 * Organisation settings — the per-org config that makes DOCex any client's
 * AI auditor. The org defines its name and its default approval chain (its
 * own flow chart), with a person per stage so sign-offs auto-route. New
 * rulebooks inherit this chain; nothing here is hard-coded to one org.
 */

type StageRow = { name: string; email: string };

export default function OrgSettingsPage() {
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("Payment requisition");
  const [stages, setStages] = useState<StageRow[]>([]);
  const [types, setTypes] = useState<PaymentType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getOrgProfile();
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
    setTypes((ts) => [...ts, { name: "", required_documents: [], notes: "" }]);
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
        roles: [],
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
          })),
      };
      const saved = await updateOrgProfile(profile);
      setName(saved.name);
      setSubject(saved.payment_subject ?? "Payment requisition");
      setStages(
        (saved.default_approval_workflow ?? []).map((s) => ({
          name: s,
          email: saved.directory?.[s] ?? "",
        })),
      );
      setTypes(saved.payment_types ?? []);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setSaving(false);
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
          <div className="space-y-8">
            {/* Org name */}
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

            {/* What the org calls the intake artifact */}
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

            {/* Default approval workflow + routing */}
            <section className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="flex items-start gap-3">
                <GitBranch className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div className="flex-1 space-y-1">
                  <h3 className="text-base font-semibold text-gray-900">
                    Default approval workflow
                  </h3>
                  <p className="text-sm text-gray-600">
                    Your sign-off chain — the stages every payment passes after a
                    check. New rulebooks inherit this. Add a person per stage and
                    sign-off requests route to them automatically.
                  </p>
                </div>
              </div>

              <div className="mt-5 space-y-2">
                {stages.length === 0 && (
                  <p className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-4 text-center text-xs text-gray-500">
                    No stages yet — add the first stage of your approval chain.
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

            {/* Payment types + required-doc checklists */}
            <section className="rounded-xl border border-gray-200 bg-white p-5">
              <div className="flex items-start gap-3">
                <Building2 className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div className="flex-1 space-y-1">
                  <h3 className="text-base font-semibold text-gray-900">
                    Payment types &amp; required documents
                  </h3>
                  <p className="text-sm text-gray-600">
                    Each payment type carries its own document checklist and
                    special rules. Officers pick a type when checking a payment —
                    incomplete documentation is the #1 cause of delay, so this is
                    where you stop it.
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

            <GuidanceCard title="One engine, any organisation">
              DOCex's engine is the same for everyone — what changes per client is
              this configuration. Your policies become rulebooks, your flow chart
              becomes this workflow, and your people become the routing. A second
              organisation sets their own and gets their own AI auditor.
            </GuidanceCard>

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
                Save settings
              </button>
              {saved && (
                <span className="text-sm font-medium text-emerald-600">
                  Saved ✓
                </span>
              )}
            </div>
          </div>
        )}
      </main>
    </AppShell>
  );
}
