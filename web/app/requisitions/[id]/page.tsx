"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Banknote,
  Check,
  Loader2,
  Lock,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PolicyCheckList, ReqStatusBadge } from "@/components/erp/PolicyChecks";
import {
  decideRequisition,
  getRequisition,
  newIdempotencyKey,
  payRequisition,
  resubmitRequisition,
} from "@/lib/requisitionApi";
import { dateTime, humanise, money, relativeTime } from "@/lib/requisitionFormat";
import type { Decision, Requisition } from "@/types/requisition";

/**
 * Requisition detail — where a decision actually gets made.
 *
 * The design rule on this screen: an approver can never release a blocking
 * check by accident. Releasing one requires ticking that specific check,
 * writing a reason, and naming the authority relied on. The Approve button
 * stays disabled until all three exist. The server enforces the same rules
 * (and additionally checks the step holds that authority and the amount is
 * within its limit) — the UI just refuses to send a request it knows is
 * incomplete, so the approver isn't taught to click through errors.
 */
export default function RequisitionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === "string" ? params.id : "";

  const [req, setReq] = useState<Requisition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [notes, setNotes] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideAuthority, setOverrideAuthority] = useState("");
  const [bankReference, setBankReference] = useState("");
  const [busy, setBusy] = useState<"" | Decision | "pay" | "resubmit">("");
  const [actionError, setActionError] = useState<string | null>(null);

  const payKey = useRef<string>(newIdempotencyKey());

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setReq(await getRequisition(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this requisition.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const blocking = req?.checks.filter((c) => c.result === "fail" && !c.overridden) ?? [];
  const allBlockingSelected =
    blocking.length > 0 && blocking.every((c) => selected.includes(c.code));

  // Approving over a FAIL needs the check ticked, a reason, and an authority.
  const overrideComplete =
    allBlockingSelected && overrideReason.trim().length > 0 && overrideAuthority.trim().length > 0;
  const canApprove = blocking.length === 0 || overrideComplete;

  const isOpen =
    req != null && ["submitted", "in_review"].includes(req.status);
  const canPay = req?.status === "approved";
  const canResubmit = req?.status === "returned";

  function toggle(code: string) {
    setSelected((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  }

  async function decide(decision: Decision) {
    if (!req) return;
    if (decision === "approved" && !canApprove) return;

    setBusy(decision);
    setActionError(null);
    try {
      const updated = await decideRequisition(req.id, {
        decision,
        notes,
        overrides: decision === "approved" ? selected : [],
        override_reason: decision === "approved" ? overrideReason : "",
        override_authority: decision === "approved" ? overrideAuthority : "",
      });
      setReq(updated);
      setNotes("");
      setSelected([]);
      setOverrideReason("");
      setOverrideAuthority("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not record that decision.");
    } finally {
      setBusy("");
    }
  }

  async function pay() {
    if (!req) return;
    setBusy("pay");
    setActionError(null);
    try {
      await payRequisition(req.id, bankReference.trim(), payKey.current);
      payKey.current = newIdempotencyKey();
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not record that payment.");
    } finally {
      setBusy("");
    }
  }

  async function resubmit() {
    if (!req) return;
    setBusy("resubmit");
    setActionError(null);
    try {
      setReq(await resubmitRequisition(req.id, notes));
      setNotes("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not resubmit.");
    } finally {
      setBusy("");
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 p-8 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </AppShell>
    );
  }

  if (error || !req) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl space-y-4">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            {error ?? "Requisition not found."}
          </div>
          <Link href="/requisitions" className="text-sm font-medium text-brand-600">
            ← Back to requisitions
          </Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <Link
          href="/requisitions"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 transition hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Requisitions
        </Link>

        {/* Header — the four facts a decision rests on. */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">{req.ref}</h1>
              <ReqStatusBadge status={req.status} />
            </div>
            <p className="mt-1 text-sm text-gray-600">
              {money(req.amount, req.currency)} to {req.vendor_name}
              {req.current_step ? ` — with ${humanise(req.current_step)}` : ""}
            </p>
          </div>
          <div className="text-right text-xs text-gray-500">
            <p>Raised by {req.submitted_by}</p>
            <p>
              {humanise(req.department)} · {relativeTime(req.submitted_at)}
            </p>
          </div>
        </div>

        {/* A broken chain means the record was altered outside the app. It is
            the single most serious thing this screen can say, so it is loud. */}
        {!req.audit_chain_valid ? (
          <div className="flex gap-3 rounded-lg border border-red-300 bg-red-50 p-4">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            <div>
              <p className="text-sm font-semibold text-red-900">Audit chain does not verify</p>
              <p className="mt-0.5 text-sm text-red-800">
                This record&rsquo;s history has been altered outside the application. Do not act on
                it — raise it with whoever administers this instance.
              </p>
            </div>
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <div className="space-y-6">
            <Card title="Request">
              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Detail label="Payee" value={req.vendor_name} />
                <Detail label="Amount" value={money(req.amount, req.currency)} />
                <Detail label="Category" value={humanise(req.category)} />
                <Detail label="Project / cost centre" value={req.project_code || "—"} />
                <Detail label="Grant" value={req.grant_code || "—"} />
                <Detail label="Vendor account" value={req.vendor_account || "—"} />
              </dl>
              {req.description ? (
                <p className="mt-4 border-t border-gray-100 pt-3 text-sm text-gray-700">
                  {req.description}
                </p>
              ) : null}
              {req.documents.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {req.documents.map((d) => (
                    <span
                      key={d}
                      className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600"
                    >
                      {humanise(d)}
                    </span>
                  ))}
                </div>
              ) : null}
            </Card>

            <Card
              title="Policy checks"
              subtitle={
                blocking.length > 0
                  ? `${blocking.length} ${blocking.length === 1 ? "check blocks" : "checks block"} payment`
                  : "Nothing blocks payment"
              }
            >
              <PolicyCheckList
                checks={req.checks}
                selectable={isOpen}
                selectedCodes={selected}
                onToggle={toggle}
              />
            </Card>

            {isOpen ? (
              <DecisionPanel
                blockingCount={blocking.length}
                allBlockingSelected={allBlockingSelected}
                selectedCount={selected.length}
                notes={notes}
                setNotes={setNotes}
                overrideReason={overrideReason}
                setOverrideReason={setOverrideReason}
                overrideAuthority={overrideAuthority}
                setOverrideAuthority={setOverrideAuthority}
                canApprove={canApprove}
                busy={busy}
                onDecide={decide}
                error={actionError}
              />
            ) : null}

            {canPay ? (
              <Card title="Record payment" subtitle="Freezes an immutable transaction record">
                <p className="mb-3 text-sm text-gray-600">
                  Do this once the money has actually left the account. Every check, approval and
                  audit line is copied and locked at this moment; nothing can be edited afterwards.
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="min-w-[220px] flex-1">
                    <span className="mb-1.5 block text-sm font-medium text-gray-700">
                      Bank confirmation reference
                    </span>
                    <input
                      value={bankReference}
                      onChange={(e) => setBankReference(e.target.value)}
                      placeholder="e.g. FT26081512345"
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={pay}
                    disabled={busy !== ""}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {busy === "pay" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Banknote className="h-4 w-4" />
                    )}
                    Mark as paid
                  </button>
                </div>
                {actionError ? (
                  <p className="mt-3 text-sm text-red-700">{actionError}</p>
                ) : null}
              </Card>
            ) : null}

            {canResubmit ? (
              <Card title="Resubmit" subtitle="Re-runs every policy check and re-routes it">
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  placeholder="What did you fix?"
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <button
                  type="button"
                  onClick={resubmit}
                  disabled={busy !== ""}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                >
                  {busy === "resubmit" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RotateCcw className="h-4 w-4" />
                  )}
                  Resubmit
                </button>
                {actionError ? <p className="mt-3 text-sm text-red-700">{actionError}</p> : null}
              </Card>
            ) : null}

            {req.transaction_id ? (
              <Link
                href={`/payments/${encodeURIComponent(req.transaction_id)}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
              >
                <Lock className="h-4 w-4" />
                Open the locked transaction record
              </Link>
            ) : null}
          </div>

          <div className="space-y-6">
            <Card title="Approvals">
              {req.approvals.length === 0 ? (
                <p className="text-sm text-gray-500">No decisions recorded yet.</p>
              ) : (
                <ol className="space-y-3">
                  {req.approvals.map((a, i) => (
                    <li key={`${a.step}-${a.at}-${i}`} className="border-l-2 border-gray-200 pl-3">
                      <div className="flex items-center gap-1.5">
                        {a.decision === "approved" ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : a.decision === "declined" ? (
                          <X className="h-3.5 w-3.5 text-red-600" />
                        ) : (
                          <RotateCcw className="h-3.5 w-3.5 text-orange-600" />
                        )}
                        <span className="text-sm font-medium text-gray-900">
                          {humanise(a.step)}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-600">
                        {a.actor} · {humanise(a.department)}
                      </p>
                      <p className="text-xs text-gray-400">{dateTime(a.at)}</p>
                      {a.notes ? (
                        <p className="mt-1 text-xs text-gray-700">&ldquo;{a.notes}&rdquo;</p>
                      ) : null}
                      {a.overrides.length ? (
                        <p className="mt-1 text-xs font-medium text-purple-700">
                          Released: {a.overrides.join(", ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </Card>

            <Card
              title="Audit log"
              subtitle={req.audit_chain_valid ? "Hash chain verified" : "Chain broken"}
            >
              <div className="mb-3 flex items-center gap-1.5 text-xs">
                {req.audit_chain_valid ? (
                  <>
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                    <span className="font-medium text-emerald-700">
                      Append-only and unaltered
                    </span>
                  </>
                ) : (
                  <>
                    <ShieldAlert className="h-3.5 w-3.5 text-red-600" />
                    <span className="font-medium text-red-700">Tampering detected</span>
                  </>
                )}
              </div>
              <ol className="space-y-2.5">
                {req.audit_log.map((e) => (
                  <li key={e.seq} className="text-xs">
                    <p className="font-medium text-gray-900">{humanise(e.event)}</p>
                    {e.detail ? <p className="text-gray-600">{e.detail}</p> : null}
                    <p className="text-gray-400">
                      {e.actor ? `${e.actor} · ` : ""}
                      {dateTime(e.at)}
                    </p>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ─── decision panel ─────────────────────────────────────────────────────────

function DecisionPanel({
  blockingCount,
  allBlockingSelected,
  selectedCount,
  notes,
  setNotes,
  overrideReason,
  setOverrideReason,
  overrideAuthority,
  setOverrideAuthority,
  canApprove,
  busy,
  onDecide,
  error,
}: {
  blockingCount: number;
  allBlockingSelected: boolean;
  selectedCount: number;
  notes: string;
  setNotes: (v: string) => void;
  overrideReason: string;
  setOverrideReason: (v: string) => void;
  overrideAuthority: string;
  setOverrideAuthority: (v: string) => void;
  canApprove: boolean;
  busy: string;
  onDecide: (d: Decision) => void;
  error: string | null;
}) {
  return (
    <Card title="Your decision">
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-gray-700">
          Notes for the next approver and the auditor
        </span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </label>

      {blockingCount > 0 ? (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3.5">
          <p className="text-sm font-semibold text-red-900">
            {blockingCount} {blockingCount === 1 ? "check blocks" : "checks block"} this payment
          </p>
          <p className="mt-1 text-sm text-red-800">
            To approve anyway, tick every blocking check above, then say why and under whose
            authority. This is recorded against your name and read at audit.
          </p>

          <p className="mt-2.5 text-xs font-medium text-red-900">
            {allBlockingSelected
              ? `All ${blockingCount} selected.`
              : `${selectedCount} of ${blockingCount} selected — tick the rest above.`}
          </p>

          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-red-900">
                Why is this being released?
              </span>
              <textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                rows={2}
                placeholder="A reason an auditor would accept twelve months from now."
                className="w-full rounded-lg border border-red-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-red-900">
                Authority relied on
              </span>
              <input
                value={overrideAuthority}
                onChange={(e) => setOverrideAuthority(e.target.value)}
                placeholder="e.g. ED — delegation of authority up to ₦200,000"
                className="w-full rounded-lg border border-red-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
              />
            </label>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2.5">
        <button
          type="button"
          onClick={() => onDecide("approved")}
          disabled={!canApprove || busy !== ""}
          title={
            canApprove
              ? undefined
              : "Tick every blocking check and record a reason and authority first."
          }
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "approved" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Check className="h-4 w-4" />
          )}
          {blockingCount > 0 ? "Approve with override" : "Approve"}
        </button>
        <button
          type="button"
          onClick={() => onDecide("returned")}
          disabled={busy !== ""}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
        >
          {busy === "returned" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RotateCcw className="h-4 w-4" />
          )}
          Return for fixes
        </button>
        <button
          type="button"
          onClick={() => onDecide("declined")}
          disabled={busy !== ""}
          className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-50"
        >
          {busy === "declined" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <X className="h-4 w-4" />
          )}
          Decline
        </button>
      </div>
    </Card>
  );
}

// ─── small pieces ───────────────────────────────────────────────────────────

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-gray-500">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-900">{value}</dd>
    </div>
  );
}
