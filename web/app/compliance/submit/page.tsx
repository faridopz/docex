"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckSquare,
  Info,
  Loader2,
  Send,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DropZone } from "@/components/DropZone";
import { DynamicFormFields } from "@/components/compliance/DynamicFormFields";
import { GuidanceCard } from "@/components/GuidanceCard";
import {
  checkPaymentForm,
  checkPaymentSingle,
  getOrgProfile,
  listRulebooks,
  precheckDocs,
  routePayment,
  type PrecheckResult,
  type RequisitionContext,
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
  // The org's live "choices_source" lists, keyed the same way FormFieldSpec
  // marks them. Today just the approved vendor list, but this shape
  // extends to any future live-list source without touching the renderer.
  const [approvedVendors, setApprovedVendors] = useState<string[]>([]);

  const [selectedType, setSelectedType] = useState("");
  const [label, setLabel] = useState("");
  const [department, setDepartment] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  // Values for a "form" or "hybrid" payment type's structured fields,
  // keyed by FormFieldSpec.name. Generic — whatever fields the selected
  // type asks for, this is where their values live. Cleared whenever the
  // selected type changes so a stale field from a previous type can't leak
  // into a new submission.
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  useEffect(() => {
    setFormValues({});
  }, [selectedType]);

  // Requisition context — the fields that used to require an uploaded
  // "Payment Requisition Form" PDF for the AI to parse. Optional: an org
  // that doesn't care about donor coding or a formal approver-of-record
  // can leave these blank and nothing changes for them. requisitionDate
  // defaults to today so the common case needs zero typing.
  const [requisitionDate, setRequisitionDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [billingDonor, setBillingDonor] = useState("");
  const [approvedBy, setApprovedBy] = useState("");

  const [phase, setPhase] = useState<Phase>("form");
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rulebooks, setRulebooks] = useState<RulebookSummary[]>([]);
  const [precheck, setPrecheck] = useState<PrecheckResult | null>(null);
  const [prechecking, setPrechecking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getOrgProfile();
        if (cancelled) return;
        setSubject(p.payment_subject || "Payment requisition");
        setTypes(p.payment_types ?? []);
        setApprovedVendors(p.approved_vendors ?? []);
      } catch {
        /* types are optional — the form still works without them */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Instant, deterministic completeness pre-check (no LLM) whenever the type +
  // files are set. Tells the submitter what's missing before they submit.
  useEffect(() => {
    let cancelled = false;
    if (!selectedType || files.length === 0) {
      setPrecheck(null);
      return;
    }
    setPrechecking(true);
    (async () => {
      try {
        const r = await precheckDocs(files, selectedType);
        if (!cancelled) setPrecheck(r);
      } catch {
        if (!cancelled) setPrecheck(null);
      } finally {
        if (!cancelled) setPrechecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [files, selectedType]);

  const current = types.find((t) => t.name === selectedType);
  // Every payment type defaults to "document" (see PaymentType.intake_mode)
  // so a type with no intake_mode set at all — or no type selected yet —
  // behaves exactly like the original document-only flow.
  const intakeMode = current?.intake_mode ?? "document";
  const usesForm = intakeMode === "form" || intakeMode === "hybrid";
  const usesDocs = intakeMode === "document" || intakeMode === "hybrid";
  const requiredFormFields = current?.form_fields.filter((f) => f.required) ?? [];
  const formFieldsFilled = requiredFormFields.every((f) =>
    (formValues[f.name] ?? "").trim().length > 0,
  );
  const canSubmit =
    label.trim().length > 0 &&
    (!usesDocs || files.length > 0) &&
    (!usesForm || formFieldsFilled);

  function fullLabel(): string {
    const base = label.trim();
    const parts = [base];
    if (selectedType) parts.unshift(selectedType);
    if (department.trim()) parts.push(department.trim());
    return parts.join(" · ");
  }

  function requisitionContext(): RequisitionContext {
    // label and department already ask exactly what payment_purpose and
    // requested_by need — reusing them here means the officer isn't asked
    // the same question twice under two different names.
    return {
      requisitionDate: requisitionDate || undefined,
      billingDonor: billingDonor.trim() || undefined,
      paymentPurpose: label.trim() || undefined,
      requestedBy: department.trim() || undefined,
      approvedBy: approvedBy.trim() || undefined,
    };
  }

  async function runAgainst(rulebookId: string) {
    setPhase("working");
    setStatusMsg("Checking against your policy…");
    try {
      const result = await checkPaymentSingle(
        rulebookId,
        fullLabel(),
        files,
        requisitionContext(),
      );
      router.push(`/compliance/checks/${result.payment_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The check failed.");
      setPhase("error");
    }
  }

  async function submit() {
    if (!canSubmit) return;
    setError(null);

    // Form and hybrid types skip document-based routing entirely — the
    // backend resolves the rulebook from the payment type's own
    // default_rulebook_id (or, for hybrid, from any attached documents).
    // There's no "picking" step here: a form type with no rulebook wired
    // up is a configuration gap for whoever set up the payment type, not
    // something the submitter should have to resolve.
    if (usesForm) {
      setPhase("working");
      setStatusMsg(
        usesDocs ? "Checking your submission…" : "Checking your request…",
      );
      try {
        const result = await checkPaymentForm(
          selectedType,
          fullLabel(),
          formValues,
          usesDocs ? files : [],
        );
        router.push(`/compliance/checks/${result.payment_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "The check failed.");
        setPhase("error");
      }
      return;
    }

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

                {current && usesDocs && (
                  <div className="mt-2 space-y-2 rounded-xl border border-brand-100 bg-brand-50/40 p-3">
                    <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand-700">
                      Documents to attach
                      {prechecking && (
                        <Loader2 className="h-3 w-3 animate-spin text-brand-400" />
                      )}
                    </p>
                    <ul className="space-y-1">
                      {current.required_documents.map((d) => {
                        const found = precheck
                          ? precheck.present.includes(d)
                          : null;
                        return (
                          <li
                            key={d}
                            className="flex items-center gap-2 text-sm"
                          >
                            {found === true ? (
                              <CheckSquare className="h-4 w-4 shrink-0 text-emerald-600" />
                            ) : found === false ? (
                              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
                            ) : (
                              <CheckSquare className="h-4 w-4 shrink-0 text-brand-500" />
                            )}
                            <span
                              className={
                                found === false ? "text-amber-800" : "text-gray-700"
                              }
                            >
                              {d}
                              {found === false && " — not detected"}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                    {precheck && !precheck.complete && (
                      <p className="rounded-md bg-amber-100 px-2.5 py-1.5 text-xs font-medium text-amber-900">
                        {precheck.missing.length} required document
                        {precheck.missing.length === 1 ? "" : "s"} not detected.
                        You can still submit — but incomplete bundles get sent
                        back, so attach what&apos;s missing if you can.
                      </p>
                    )}
                    {precheck && precheck.complete && (
                      <p className="rounded-md bg-emerald-100 px-2.5 py-1.5 text-xs font-medium text-emerald-900">
                        All required documents detected. ✓
                      </p>
                    )}
                    {current.notes && (
                      <p className="flex items-start gap-1.5 text-xs text-amber-800">
                        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        {current.notes}
                      </p>
                    )}
                  </div>
                )}

                {/* Form-mode types have no document checklist, but the
                    org's notes (e.g. "retire within 5 working days") are
                    still worth showing. */}
                {current && !usesDocs && current.notes && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-xl border border-amber-100 bg-amber-50/60 p-3 text-xs text-amber-800">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {current.notes}
                  </p>
                )}
              </section>
            )}

            {/* 1b. Structured fields — form or hybrid payment types. Renders
                entirely from PaymentType.form_fields, so this works for any
                org's own payment type, not just a built-in one. */}
            {current && usesForm && current.form_fields.length > 0 && (
              <section className="space-y-2">
                <label className="block text-sm font-semibold text-gray-900">
                  Details
                </label>
                <DynamicFormFields
                  fields={current.form_fields}
                  values={formValues}
                  onChange={(name, value) =>
                    setFormValues((prev) => ({ ...prev, [name]: value }))
                  }
                  liveChoices={{ org_approved_vendors: approvedVendors }}
                />
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

            {/* 2b. Requisition details — optional, structured. Replaces
                having to upload a scanned Payment Requisition Form for the
                AI to read these back out of a PDF. Document-mode only: a
                form/hybrid type's /check/form endpoint doesn't take these
                fields — whatever context it needs is part of form_fields
                instead, so this section would be silently ignored there. */}
            {intakeMode === "document" && (
            <section className="grid gap-4 rounded-xl border border-gray-200 bg-gray-50/60 p-4 sm:grid-cols-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 sm:col-span-2">
                Requisition details{" "}
                <span className="font-normal normal-case text-gray-400">
                  (optional)
                </span>
              </p>
              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-gray-900">
                  Date
                </label>
                <input
                  type="date"
                  value={requisitionDate}
                  onChange={(e) => setRequisitionDate(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-semibold text-gray-900">
                  Billing donor / fund
                </label>
                <input
                  type="text"
                  value={billingDonor}
                  onChange={(e) => setBillingDonor(e.target.value)}
                  placeholder="e.g. USAID, Gates Foundation"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-sm font-semibold text-gray-900">
                  Requisition approved by
                </label>
                <input
                  type="text"
                  value={approvedBy}
                  onChange={(e) => setApprovedBy(e.target.value)}
                  placeholder="e.g. Tunde Balogun, Head of Operations"
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            </section>
            )}

            {/* 3. Upload — document and hybrid types only. A pure form
                type has nothing for this section to collect. */}
            {usesDocs && (
            <section className="space-y-2">
              <label className="block text-sm font-semibold text-gray-900">
                Attach all the documents
              </label>
              <p className="text-xs text-gray-500">
                PDF, DOCX, or TXT — drop everything in together.
              </p>
              <DropZone files={files} onFilesChange={setFiles} />
            </section>
            )}

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
              {usesDocs
                ? "DOCex auto-selects the policy from your documents"
                : "DOCex checks this instantly against your policy"}
            </p>
          </div>
        )}
      </main>
    </AppShell>
  );
}
