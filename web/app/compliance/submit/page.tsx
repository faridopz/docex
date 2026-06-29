"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckSquare,
  Info,
  Loader2,
  Send,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { GuidanceCard } from "@/components/GuidanceCard";
import {
  checkPaymentSingle,
  getOrgProfile,
  listRulebooks,
  routePayment,
} from "@/lib/api";
import type { PaymentType, RulebookSummary } from "@/types";

/**
 * Submit a requisition — the dead-simple intake for anyone in any department.
 *
 * No rulebook knowledge required: pick the type of payment, see exactly which
 * documents it needs, drop them in, submit. DOCex auto-routes the bundle to
 * the right policy (the router), runs the check, and drops you on the result.
 */

type Phase = "form" | "working" | "picking" | "error";

export default function SubmitRequisitionPage() {
  const router = useRouter();

  const [subject, setSubject] = useState("Payment requisition");
  const [types, setTypes] = useState<PaymentType[]>([]);

  const [selectedType, setSelectedType] = useState("");
  const [label, setLabel] = useState("");
  const [department, setDepartment] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  const [phase, setPhase] = useState<Phase>("form");
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rulebooks, setRulebooks] = useState<RulebookSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getOrgProfile();
        if (cancelled) return;
        setSubject(p.payment_subject || "Payment requisition");
        setTypes(p.payment_types ?? []);
      } catch {
        /* types are optional — the form still works without them */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const current = types.find((t) => t.name === selectedType);
  const canSubmit = label.trim().length > 0 && files.length > 0;

  function fullLabel(): string {
    const base = label.trim();
    const parts = [base];
    if (selectedType) parts.unshift(selectedType);
    if (department.trim()) parts.push(department.trim());
    return parts.join(" · ");
  }

  async function runAgainst(rulebookId: string) {
    setPhase("working");
    setStatusMsg("Checking against your policy…");
    try {
      const result = await checkPaymentSingle(rulebookId, fullLabel(), files);
      router.push(`/compliance/checks/${result.payment_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The check failed.");
      setPhase("error");
    }
  }

  async function submit() {
    if (!canSubmit) return;
    setError(null);
    setPhase("working");
    setStatusMsg("Finding the right policy for these documents…");
    try {
      const suggestions = await routePayment(files);
      const strong = suggestions.filter(
        (s) => s.confidence === "high" || s.confidence === "medium",
      );
      if (strong.length >= 1) {
        await runAgainst(strong[0].rulebook_id);
        return;
      }
      // No confident auto-match — fall back to a quick policy pick.
      const rbs = await listRulebooks();
      setRulebooks(rbs);
      if (rbs.length === 1) {
        await runAgainst(rbs[0].id);
        return;
      }
      if (rbs.length === 0) {
        setError(
          "No policy sets exist yet. Ask your compliance officer to add one first.",
        );
        setPhase("error");
        return;
      }
      setPhase("picking");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit.");
      setPhase("error");
    }
  }

  return (
    <AppShell active="submit">
      <main className="mx-auto max-w-2xl px-6 py-10">
        {phase === "working" ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Loader2 className="mb-6 h-10 w-10 animate-spin text-brand-600" />
            <p className="text-lg font-semibold text-gray-900">{statusMsg}</p>
            <p className="mt-2 text-sm text-gray-600">
              This usually takes under a minute.
            </p>
          </div>
        ) : phase === "picking" ? (
          <div className="space-y-4">
            <h1 className="text-2xl font-bold text-gray-900">
              Which policy applies?
            </h1>
            <p className="text-sm text-gray-600">
              We couldn&apos;t auto-match a policy from the documents. Pick the
              one this requisition should be checked against.
            </p>
            <div className="space-y-2">
              {rulebooks.map((rb) => (
                <button
                  key={rb.id}
                  type="button"
                  onClick={() => runAgainst(rb.id)}
                  className="flex w-full items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-left transition hover:border-brand-300 hover:shadow-card-hover"
                >
                  <span className="text-sm font-semibold text-gray-900">
                    {rb.name}
                  </span>
                  <span className="text-xs text-gray-500">
                    {rb.active_rule_count} rules
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-8">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Submit a {subject.toLowerCase()}
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Pick the type, attach the documents, submit. DOCex figures out
                which policy applies and checks it — you don&apos;t need to know
                the rules.
              </p>
            </div>

            {/* 1. Type */}
            {types.length > 0 && (
              <section className="space-y-2">
                <label className="block text-sm font-semibold text-gray-900">
                  What kind of payment is this?
                </label>
                <select
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                >
                  <option value="">Select a type…</option>
                  {types.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </select>

                {current && (
                  <div className="mt-2 space-y-2 rounded-xl border border-brand-100 bg-brand-50/40 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">
                      Documents to attach
                    </p>
                    <ul className="space-y-1">
                      {current.required_documents.map((d) => (
                        <li
                          key={d}
                          className="flex items-center gap-2 text-sm text-gray-700"
                        >
                          <CheckSquare className="h-4 w-4 shrink-0 text-brand-500" />
                          {d}
                        </li>
                      ))}
                    </ul>
                    {current.notes && (
                      <p className="flex items-start gap-1.5 text-xs text-amber-800">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        {current.notes}
                      </p>
                    )}
                  </div>
                )}
              </section>
            )}

            {/* 2. What & who */}
            <section className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-sm font-semibold text-gray-900">
                  What&apos;s this for?
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. Workshop catering — April training"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-sm font-semibold text-gray-900">
                  Department / requested by{" "}
                  <span className="font-normal text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="e.g. Operations — Aisha"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            </section>

            {/* 3. Upload */}
            <section className="space-y-2">
              <label className="block text-sm font-semibold text-gray-900">
                Attach all the documents
              </label>
              <p className="text-xs text-gray-500">
                PDF, DOCX, or TXT — drop everything in together.
              </p>
              <DropZone files={files} onFilesChange={setFiles} />
            </section>

            <GuidanceCard title="One inbox for every department">
              Procurement, travel, participant payments, consultant invoices —
              whatever the request, it comes in here. DOCex routes each one to
              the right policy automatically, so the requester never has to.
            </GuidanceCard>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            <div className="flex justify-end border-t border-gray-200 pt-6">
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
              >
                <Send className="h-4 w-4" />
                Submit &amp; check
              </button>
            </div>
            <p className="-mt-4 flex items-center justify-end gap-1.5 text-xs text-gray-400">
              <Sparkles className="h-3.5 w-3.5" />
              DOCex auto-selects the policy from your documents
            </p>
          </div>
        )}
      </main>
    </AppShell>
  );
}
