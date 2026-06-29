"use client";

import { useState } from "react";
import { AlertTriangle, Check, Loader2, Plus, ShieldAlert } from "lucide-react";
import { addRisk, updateRisk, type RiskInput } from "@/lib/api";
import type {
  ComplianceCheckResult,
  RiskEntry,
  RiskSeverity,
  RiskStatus,
} from "@/types";

/**
 * Risk & Actions register for a compliance check.
 *
 * The officer's core job: did this surface a risk? what was it, how severe,
 * what action was taken, was it escalated, what's the plan, and is it
 * resolved? Every entry is mirrored to the decision log, so it lands in the
 * audit trail and the exported report.
 */

const SEV_STYLE: Record<RiskSeverity, string> = {
  high: "bg-rose-100 text-rose-800 ring-rose-200",
  medium: "bg-amber-100 text-amber-800 ring-amber-200",
  low: "bg-gray-100 text-gray-700 ring-gray-200",
};

const STATUS_STYLE: Record<RiskStatus, string> = {
  open: "bg-rose-50 text-rose-700",
  in_progress: "bg-amber-50 text-amber-700",
  resolved: "bg-emerald-50 text-emerald-700",
};

const STATUS_LABEL: Record<RiskStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
};

export function RiskPanel({
  check,
  onUpdate,
}: {
  check: ComplianceCheckResult;
  onUpdate: (updated: ComplianceCheckResult) => void;
}) {
  const risks = check.risks ?? [];
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New-risk form state
  const [desc, setDesc] = useState("");
  const [severity, setSeverity] = useState<RiskSeverity>("medium");
  const [actionTaken, setActionTaken] = useState("");
  const [escalated, setEscalated] = useState(false);
  const [escalatedTo, setEscalatedTo] = useState("");
  const [actionPlan, setActionPlan] = useState("");

  const openCount = risks.filter((r) => r.status !== "resolved").length;

  async function submitNew() {
    if (!desc.trim()) {
      setError("Describe the risk first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body: RiskInput = {
        description: desc.trim(),
        severity,
        action_taken: actionTaken.trim() || null,
        escalated,
        escalated_to: escalated ? escalatedTo.trim() || null : null,
        action_plan: actionPlan.trim() || null,
      };
      const updated = await addRisk(check.payment_id, body);
      onUpdate(updated);
      setDesc("");
      setSeverity("medium");
      setActionTaken("");
      setEscalated(false);
      setEscalatedTo("");
      setActionPlan("");
      setAdding(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log the risk.");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(risk: RiskEntry, status: RiskStatus) {
    setBusy(true);
    setError(null);
    try {
      const updated = await updateRisk(check.payment_id, risk.id, {
        description: risk.description,
        status,
      });
      onUpdate(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the risk.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-brand-600" />
          <h3 className="text-base font-semibold text-gray-900">
            Risk &amp; actions
          </h3>
          <span className="text-xs text-gray-500">
            {risks.length === 0
              ? "no risks logged"
              : `${risks.length} logged · ${openCount} open`}
          </span>
        </div>
        {!adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
          >
            <Plus className="h-4 w-4" />
            Log a risk
          </button>
        )}
      </div>

      {risks.length === 0 && !adding && (
        <p className="mt-4 rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-4 text-center text-xs text-gray-500">
          No risks identified yet. If this check surfaced one, log it — what it
          is, what you did, whether you escalated, and the plan.
        </p>
      )}

      {/* Existing risks */}
      {risks.length > 0 && (
        <div className="mt-4 space-y-3">
          {risks.map((r) => (
            <div
              key={r.id}
              className="rounded-xl border border-gray-200 p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ${SEV_STYLE[r.severity]}`}
                >
                  <AlertTriangle className="h-3 w-3" />
                  {r.severity}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[r.status]}`}
                >
                  {STATUS_LABEL[r.status]}
                </span>
                {r.escalated && (
                  <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700">
                    Escalated{r.escalated_to ? ` → ${r.escalated_to}` : ""}
                  </span>
                )}
              </div>

              <p className="mt-2 text-sm font-medium text-gray-900">
                {r.description}
              </p>
              {r.action_taken && (
                <p className="mt-1 text-sm text-gray-600">
                  <span className="font-medium text-gray-700">Action taken:</span>{" "}
                  {r.action_taken}
                </p>
              )}
              {r.action_plan && (
                <p className="mt-1 text-sm text-gray-600">
                  <span className="font-medium text-gray-700">Action plan:</span>{" "}
                  {r.action_plan}
                </p>
              )}

              {r.status !== "resolved" && (
                <div className="mt-3 flex items-center gap-2">
                  {r.status === "open" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => setStatus(r, "in_progress")}
                      className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:border-amber-300 hover:text-amber-700 disabled:opacity-50"
                    >
                      Mark in progress
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setStatus(r, "resolved")}
                    className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-50"
                  >
                    <Check className="h-3.5 w-3.5" />
                    Mark resolved
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* New-risk form */}
      {adding && (
        <div className="mt-4 space-y-3 rounded-xl border border-brand-100 bg-brand-50/40 p-4">
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            rows={2}
            placeholder="What is the risk? e.g. 'Only 2 quotations for a ₦4M purchase — below the 3-quote threshold.'"
            className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-gray-600">
                Severity
              </span>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as RiskSeverity)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              >
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
            <label className="flex items-end gap-2 pb-2">
              <input
                type="checkbox"
                checked={escalated}
                onChange={(e) => setEscalated(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              <span className="text-sm text-gray-700">Escalated</span>
            </label>
          </div>
          {escalated && (
            <input
              type="text"
              value={escalatedTo}
              onChange={(e) => setEscalatedTo(e.target.value)}
              placeholder="Escalated to — e.g. Head of Finance"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          )}
          <input
            type="text"
            value={actionTaken}
            onChange={(e) => setActionTaken(e.target.value)}
            placeholder="Action taken (optional)"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <input
            type="text"
            value={actionPlan}
            onChange={(e) => setActionPlan(e.target.value)}
            placeholder="Action plan (optional) — how it'll be dealt with"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />

          {error && <p className="text-xs text-rose-600">{error}</p>}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={submitNew}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Log risk
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setError(null);
              }}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition hover:text-gray-900"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && !adding && <p className="mt-3 text-xs text-rose-600">{error}</p>}
    </section>
  );
}
