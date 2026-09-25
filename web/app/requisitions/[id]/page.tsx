"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowLeftRight,
  Banknote,
  Check,
  Download,
  Loader2,
  Lock,
  MessageSquare,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Paperclip,
  Sparkles,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { PolicyCheckList, ReqStatusBadge } from "@/components/erp/PolicyChecks";
import {
  addRequisitionComment,
  decideRequisition,
  downloadRequisitionAttachment,
  downloadPayeeSchedule,
  downloadRequisitionExport,
  downloadRequisitionVoucher,
  getDocumentPermissions,
  getRequisition,
  getWorkflow,
  listComplianceRulebooks,
  newIdempotencyKey,
  payRequisition,
  placeRequisitionOnHold,
  releaseRequisitionHold,
  resubmitRequisition,
  requestRequisitionSignoff,
  routeRequisition,
  runComplianceCheck,
  triggerBlobDownload,
  uploadRequisitionAttachment,
  type SignoffRequestResult,
} from "@/lib/requisitionApi";
import { getClientConfig, hasFeature } from "@/lib/orgConfig";
import { dateTime, humanise, money, relativeTime } from "@/lib/requisitionFormat";
import type {
  Decision,
  Requisition,
  RequisitionWorkflow,
  RulebookSummary,
} from "@/types/requisition";

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
  const [holdReason, setHoldReason] = useState("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [holdEnabled, setHoldEnabled] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  const [commentError, setCommentError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | Decision | "pay" | "resubmit" | "hold" | "release">("");
  const [actionError, setActionError] = useState<string | null>(null);

  const [attachmentsEnabled, setAttachmentsEnabled] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [complianceEnabled, setComplianceEnabled] = useState(false);
  const [complianceBusy, setComplianceBusy] = useState(false);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [rulebooks, setRulebooks] = useState<RulebookSummary[]>([]);
  const [selectedRulebookId, setSelectedRulebookId] = useState<string>("");

  // The org's approval chain. Needed here — not just on the raise form — to
  // answer "who owns each stage, and where is this right now", which is the
  // question everyone opens a requisition to answer.
  const [workflow, setWorkflow] = useState<RequisitionWorkflow | null>(null);

  // Moving it along the chain without deciding it — escalate to a later
  // stage, or hand it back to an earlier one.
  const [routeTarget, setRouteTarget] = useState("");
  const [routeReason, setRouteReason] = useState("");
  const [routeBusy, setRouteBusy] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  // Emailed sign-off — escalate, delegate, or send this to someone who has
  // no DOCex account (a travelling AED, an auditor, a board member).
  const [signoffEmail, setSignoffEmail] = useState("");
  const [signoffNote, setSignoffNote] = useState("");
  const [signoffBusy, setSignoffBusy] = useState(false);
  const [signoffError, setSignoffError] = useState<string | null>(null);
  const [signoffResult, setSignoffResult] = useState<SignoffRequestResult | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  const [exportEnabled, setExportEnabled] = useState(false);
  const [exportBusy, setExportBusy] = useState<"" | "pdf" | "xlsx">("");
  const [exportError, setExportError] = useState<string | null>(null);

  // The organisation's own paperwork: the payment voucher, and for bulk
  // payments the schedule Finance pays from. Which buttons appear is the
  // server's answer (flag + who you are); the status rules below mirror the
  // routes so a button never shows where it would be refused.
  const [docPerms, setDocPerms] = useState<{ voucher: boolean; payee_schedule: boolean }>({
    voucher: false,
    payee_schedule: false,
  });
  const [docBusy, setDocBusy] = useState<"" | "voucher" | "schedule">("");
  const [docError, setDocError] = useState<string | null>(null);

  const payKey = useRef<string>(newIdempotencyKey());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await getClientConfig();
        if (!cancelled) {
          setHoldEnabled(hasFeature(cfg, "requisition_hold"));
          setAttachmentsEnabled(hasFeature(cfg, "requisition_attachments"));
          setComplianceEnabled(hasFeature(cfg, "requisition_compliance_check"));
          setExportEnabled(hasFeature(cfg, "requisition_export"));
          if (hasFeature(cfg, "requisition_compliance_check")) {
            try {
              const rbs = await listComplianceRulebooks();
              if (!cancelled) setRulebooks(rbs);
            } catch {
              /* the picker just stays empty — "workflow default" still works */
            }
          }
        }
      } catch {
        /* stays hidden — matches what the server would refuse anyway */
      }
      try {
        const wf = await getWorkflow();
        if (!cancelled) setWorkflow(wf);
      } catch {
        /* the route card just doesn't render; the rest of the page is fine */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
  const isHeld = req?.status === "on_hold";
  const canHold = req?.status === "in_review" && holdEnabled;

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

  async function placeHold() {
    if (!req || !holdReason.trim()) return;
    setBusy("hold");
    setActionError(null);
    try {
      setReq(await placeRequisitionOnHold(req.id, holdReason.trim()));
      setHoldReason("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not put this on hold.");
    } finally {
      setBusy("");
    }
  }

  async function releaseHold() {
    if (!req) return;
    setBusy("release");
    setActionError(null);
    try {
      setReq(await releaseRequisitionHold(req.id, releaseNotes.trim()));
      setReleaseNotes("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not release the hold.");
    } finally {
      setBusy("");
    }
  }

  async function postComment() {
    if (!req || !commentText.trim()) return;
    setCommentBusy(true);
    setCommentError(null);
    try {
      setReq(await addRequisitionComment(req.id, commentText.trim()));
      setCommentText("");
    } catch (e) {
      setCommentError(e instanceof Error ? e.message : "Could not post that comment.");
    } finally {
      setCommentBusy(false);
    }
  }

  async function handleUpload(file: File) {
    if (!req) return;
    setUploadBusy(true);
    setUploadError(null);
    try {
      setReq(await uploadRequisitionAttachment(req.id, file));
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Could not upload that file.");
    } finally {
      setUploadBusy(false);
      // Let the same file be picked again (e.g. after fixing an error).
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDownload(attachmentId: string, filename: string) {
    if (!req) return;
    setDownloadingId(attachmentId);
    setUploadError(null);
    try {
      const blob = await downloadRequisitionAttachment(req.id, attachmentId);
      triggerBlobDownload(blob, filename);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Could not download that file.");
    } finally {
      setDownloadingId(null);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getDocumentPermissions()
      .then((p) => {
        if (!cancelled) setDocPerms(p);
      })
      .catch(() => {
        /* no buttons rather than buttons that fail */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDocument(kind: "voucher" | "schedule") {
    if (!req) return;
    setDocBusy(kind);
    setDocError(null);
    try {
      const { blob, filename } =
        kind === "voucher"
          ? await downloadRequisitionVoucher(req.id, req.ref)
          : await downloadPayeeSchedule(req.id, req.ref);
      triggerBlobDownload(blob, filename);
    } catch (e) {
      setDocError(e instanceof Error ? e.message : "Could not download this document.");
    } finally {
      setDocBusy("");
    }
  }

  async function handleExport(format: "pdf" | "xlsx") {
    if (!req) return;
    setExportBusy(format);
    setExportError(null);
    try {
      const blob = await downloadRequisitionExport(req.id, format);
      triggerBlobDownload(blob, `${req.ref}.${format}`);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Could not export this requisition.");
    } finally {
      setExportBusy("");
    }
  }

  async function handleRoute() {
    if (!req || !routeTarget || routeReason.trim() === "") return;
    setRouteBusy(true);
    setRouteError(null);
    try {
      setReq(await routeRequisition(req.id, {
        target_step: routeTarget,
        reason: routeReason.trim(),
      }));
      setRouteTarget("");
      setRouteReason("");
    } catch (e) {
      setRouteError(e instanceof Error ? e.message : "Could not move this requisition.");
    } finally {
      setRouteBusy(false);
    }
  }

  async function sendForSignoff() {
    if (!req || !req.current_step) return;
    setSignoffBusy(true);
    setSignoffError(null);
    setSignoffResult(null);
    setLinkCopied(false);
    try {
      const res = await requestRequisitionSignoff(req.id, {
        step: req.current_step,
        approver_email: signoffEmail.trim(),
        note: signoffNote.trim(),
      });
      setSignoffResult(res);
      setSignoffEmail("");
      setSignoffNote("");
      // The delegation is now on the audit trail — reload so it shows.
      setReq(await getRequisition(req.id));
    } catch (e) {
      setSignoffError(e instanceof Error ? e.message : "Could not send that request.");
    } finally {
      setSignoffBusy(false);
    }
  }

  async function runCompliance() {
    if (!req) return;
    setComplianceBusy(true);
    setComplianceError(null);
    try {
      setReq(await runComplianceCheck(req.id, selectedRulebookId || undefined));
    } catch (e) {
      setComplianceError(e instanceof Error ? e.message : "Could not run the compliance check.");
    } finally {
      setComplianceBusy(false);
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
            {exportEnabled ? (
              <div className="mt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => handleExport("pdf")}
                  disabled={exportBusy !== ""}
                  className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
                >
                  {exportBusy === "pdf" ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Download className="h-3 w-3" />
                  )}
                  PDF
                </button>
                <button
                  type="button"
                  onClick={() => handleExport("xlsx")}
                  disabled={exportBusy !== ""}
                  className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
                >
                  {exportBusy === "xlsx" ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Download className="h-3 w-3" />
                  )}
                  Excel
                </button>
              </div>
            ) : null}
            {exportError ? <p className="mt-1 text-red-700">{exportError}</p> : null}
            {/* Voucher: from submission on, never a draft or a declined payment.
                Payee schedule: only once fully approved — it is what money is
                sent from. Both mirror the server, which re-checks. */}
            {(() => {
              const showVoucher =
                docPerms.voucher && req.status !== "draft" && req.status !== "declined";
              const showSchedule =
                docPerms.payee_schedule && (req.status === "approved" || req.status === "paid");
              if (!showVoucher && !showSchedule) return null;
              return (
                <div className="mt-2 flex flex-wrap justify-end gap-2">
                  {showVoucher ? (
                    <button
                      type="button"
                      onClick={() => handleDocument("voucher")}
                      disabled={docBusy !== ""}
                      className="inline-flex items-center gap-1 rounded-md border border-brand-600 bg-brand-600 px-2 py-1 text-xs font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
                    >
                      {docBusy === "voucher" ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Download className="h-3 w-3" />
                      )}
                      Payment voucher
                    </button>
                  ) : null}
                  {showSchedule ? (
                    <button
                      type="button"
                      onClick={() => handleDocument("schedule")}
                      disabled={docBusy !== ""}
                      title="Every payee with full bank details. Your download is recorded on this payment's audit trail."
                      className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
                    >
                      {docBusy === "schedule" ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Download className="h-3 w-3" />
                      )}
                      Payee schedule
                    </button>
                  ) : null}
                </div>
              );
            })()}
            {docPerms.payee_schedule && (req.status === "approved" || req.status === "paid") ? (
              <p className="mt-1 text-[11px] text-gray-400">
                Payee schedule contains full bank details; downloads are recorded.
              </p>
            ) : null}
            {docError ? <p className="mt-1 text-red-700">{docError}</p> : null}
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

        {isHeld ? (
          <div className="flex gap-3 rounded-lg border border-slate-300 bg-slate-50 p-4">
            <PauseCircle className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">
                On hold{req.current_step ? ` — still with ${humanise(req.current_step)}` : ""}
              </p>
              <p className="mt-0.5 text-sm text-slate-700">&ldquo;{req.hold_reason}&rdquo;</p>
              <p className="mt-1 text-xs text-slate-500">
                {req.held_by ? `${req.held_by} · ` : ""}
                {req.held_at ? relativeTime(req.held_at) : ""}
              </p>
              <div className="mt-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-slate-700">
                    Notes on resuming (optional)
                  </span>
                  <textarea
                    value={releaseNotes}
                    onChange={(e) => setReleaseNotes(e.target.value)}
                    rows={2}
                    placeholder="What changed, if anything."
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                </label>
                <button
                  type="button"
                  onClick={releaseHold}
                  disabled={busy !== ""}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-900 disabled:opacity-50"
                >
                  {busy === "release" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <PlayCircle className="h-4 w-4" />
                  )}
                  Release hold
                </button>
                {actionError ? <p className="mt-2 text-sm text-red-700">{actionError}</p> : null}
              </div>
            </div>
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <div className="space-y-6">
            <Card title="Request">
              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Detail label="Payee" value={req.vendor_name} />
                <Detail label="Amount" value={money(req.amount, req.currency)} />
                <Detail label="Payment type" value={humanise(req.payment_type)} />
                <Detail label="Category" value={humanise(req.category)} />
                <Detail label="Project / cost centre" value={req.project_code || "—"} />
                <Detail label="Grant" value={req.grant_code || "—"} />
                {req.payees.length === 0 ? (
                  <>
                    <Detail label="Vendor account" value={req.vendor_account || "—"} />
                    <Detail label="Bank" value={req.vendor_bank_name || "—"} />
                    <Detail label="TIN" value={req.vendor_tin || "—"} />
                    <Detail label="Phone / email" value={req.vendor_phone_or_email || "—"} />
                  </>
                ) : null}
              </dl>
              <p className="mt-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
                Amount in words: <span className="text-gray-700">{req.amount_in_words}</span>
              </p>
              {req.description ? (
                <p className="mt-3 border-t border-gray-100 pt-3 text-sm text-gray-700">
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

            {req.budget_lines.length ? (
              <Card title="Budget breakdown" subtitle="Totals are computed by the server, never typed">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-gray-500">
                      <tr>
                        <th className="py-1.5 pr-3 font-medium">Description</th>
                        <th className="py-1.5 pr-3 font-medium">Unit</th>
                        <th className="py-1.5 pr-3 font-medium">Budget line</th>
                        <th className="py-1.5 pr-3 font-medium">Qty</th>
                        <th className="py-1.5 pr-3 font-medium">Freq.</th>
                        <th className="py-1.5 pr-3 font-medium">Unit cost</th>
                        <th className="py-1.5 font-medium">Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {req.budget_lines.map((bl, i) => (
                        <tr key={i}>
                          <td className="py-1.5 pr-3 text-gray-900">{bl.description || "—"}</td>
                          <td className="py-1.5 pr-3 text-gray-600">{bl.unit || "—"}</td>
                          <td className="py-1.5 pr-3 text-gray-600">{bl.budget_line || "—"}</td>
                          <td className="py-1.5 pr-3 text-gray-600">{bl.quantity}</td>
                          <td className="py-1.5 pr-3 text-gray-600">{bl.frequency}</td>
                          <td className="py-1.5 pr-3 text-gray-600">{money(bl.unit_cost, req.currency)}</td>
                          <td className="py-1.5 font-medium text-gray-900">
                            {money(bl.line_total, req.currency)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ) : null}

            {attachmentsEnabled ? (
              <Card
                title="Attachments"
                subtitle="The real files — invoices, memos, receipts — not just a checklist label"
              >
                {req.attachments.length === 0 ? (
                  <p className="text-sm text-gray-500">Nothing attached yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {req.attachments.map((a) => (
                      <li
                        key={a.id}
                        className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <Paperclip className="h-4 w-4 shrink-0 text-gray-400" />
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-gray-900">
                              {a.filename}
                            </p>
                            <p className="text-xs text-gray-500">
                              {formatBytes(a.size)} · {a.uploaded_by} · {relativeTime(a.uploaded_at)}
                            </p>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleDownload(a.id, a.filename)}
                          disabled={downloadingId === a.id}
                          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
                        >
                          {downloadingId === a.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Download className="h-3.5 w-3.5" />
                          )}
                          Download
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 border-t border-gray-100 pt-3">
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void handleUpload(file);
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadBusy}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {uploadBusy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Paperclip className="h-3.5 w-3.5" />
                    )}
                    Attach a file
                  </button>
                  {uploadError ? <p className="mt-2 text-xs text-red-700">{uploadError}</p> : null}
                </div>
              </Card>
            ) : null}

            {complianceEnabled ? (
              <Card
                title="Compliance rulebook check"
                subtitle="AI-assisted check against the org's policy rulebook — alongside, not instead of, the checks above"
              >
                {req.compliance ? (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <ComplianceVerdictBadge verdict={req.compliance.overall_verdict} />
                      <span className="text-xs text-gray-500">
                        against &ldquo;{req.compliance.rulebook_name}&rdquo; ·{" "}
                        {req.compliance.checked_by} · {relativeTime(req.compliance.checked_at)}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700">{req.compliance.overall_summary}</p>
                    {req.compliance.results.length ? (
                      <ul className="space-y-2 border-t border-gray-100 pt-3">
                        {req.compliance.results.map((f, i) => (
                          <li key={`${f.rule_id}-${i}`} className="flex gap-2 text-sm">
                            <ComplianceVerdictBadge verdict={f.verdict} compact />
                            <div className="min-w-0">
                              <p className="text-gray-900">{f.rule_description}</p>
                              {f.reasoning ? (
                                <p className="text-xs text-gray-500">{f.reasoning}</p>
                              ) : null}
                              {f.applied_to_document ? (
                                <p className="text-xs text-gray-400">{f.applied_to_document}</p>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No compliance check has been run yet.</p>
                )}
                {rulebooks.length > 0 ? (
                  <label className="mt-3 block">
                    <span className="mb-1 block text-xs font-medium text-gray-700">
                      Check against
                    </span>
                    <select
                      value={selectedRulebookId}
                      onChange={(e) => setSelectedRulebookId(e.target.value)}
                      className="w-full max-w-xs rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-sm text-gray-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      <option value="">Workflow default</option>
                      {rulebooks.map((rb) => (
                        <option key={rb.id} value={rb.id}>
                          {rb.name} ({rb.active_rule_count} rules)
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {/* A compliance check READS the attached files. With nothing
                    attached there is nothing to read, and the server correctly
                    refuses — so offering a live button here only produces an
                    error the person could not have avoided. Say what is
                    missing instead, next to the thing that is missing. */}
                <button
                  type="button"
                  onClick={runCompliance}
                  disabled={complianceBusy || req.attachments.length === 0}
                  title={
                    req.attachments.length === 0
                      ? "Attach a file first — a compliance check reads the attached documents."
                      : undefined
                  }
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {complianceBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  {req.compliance ? "Re-run compliance check" : "Run compliance check"}
                </button>
                {req.attachments.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-500">
                    Attach at least one file above — this check reads the
                    documents, not the form.
                  </p>
                ) : null}
                {complianceError ? (
                  <p className="mt-2 text-xs text-red-700">{complianceError}</p>
                ) : null}
              </Card>
            ) : null}

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

            {canHold ? (
              <Card
                title="Not ready to decide?"
                subtitle="Pauses this at the current step — not a decision, and nothing is lost."
              >
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-gray-700">
                    Why is this on hold?
                    <span className="ml-0.5 text-red-500">*</span>
                  </span>
                  <textarea
                    value={holdReason}
                    onChange={(e) => setHoldReason(e.target.value)}
                    rows={2}
                    placeholder="What you're waiting on before you can act."
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                </label>
                <button
                  type="button"
                  onClick={placeHold}
                  disabled={busy !== "" || !holdReason.trim()}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy === "hold" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <PauseCircle className="h-4 w-4" />
                  )}
                  Put on hold
                </button>
              </Card>
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
            {/* THE APPROVAL ROUTE — who owns each stage, and where this is now.
                The raise form showed this before submitting and then it
                vanished: afterwards the page said only "with finance", a bare
                step key with no indication of who that is, what came before,
                or what happens next. This is the question everyone opens a
                payment request to answer, so it is answered on the page.

                Derived from the org's own workflow at THIS amount, so a step
                that doesn't engage below its threshold is shown as not
                required rather than silently omitted — "why didn't this go to
                the ED?" is an audit question, and the answer is visible. */}
            {workflow ? (
              <Card
                title="Approval route"
                subtitle={`This organisation's chain for ${money(req.amount, req.currency)}`}
              >
                <ApprovalRoute req={req} workflow={workflow} />
              </Card>
            ) : null}

            {/* Who is copied. The notifications already fired (they are sent
                when the requisition is raised); nobody looking at the request
                could see who got them. "Was the ED told about this?" is a
                question people ask out loud, and it has a written answer. */}
            {workflow ? <CopiedCard req={req} workflow={workflow} /> : null}

            <Card title="Decisions recorded">
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

            {/* Move it along the chain WITHOUT deciding it. The three
                decisions each move a requisition one fixed way — approve
                goes one step on, return goes all the way back to the
                submitter, decline ends it. Neither "the AED should see this
                now" nor "finance should re-check this figure" was
                expressible, and both happen constantly.

                Only shown to whoever currently holds it; the server enforces
                the same boundary, so this is not the control. */}
            {workflow && req.status === "in_review" && req.current_step ? (
              <Card
                title="Move it along the chain"
                subtitle="Escalate it, or hand it back a stage — without deciding it"
              >
                <p className="text-xs text-gray-500">
                  Sending it back to an earlier stage keeps it in review with the reviews
                  already done — unlike &ldquo;Return for fixes&rdquo;, which hands it to
                  the person who raised it. Skipping stages is recorded by name.
                </p>
                <div className="mt-3 space-y-2">
                  <select
                    value={routeTarget}
                    onChange={(e) => setRouteTarget(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  >
                    <option value="">Send to…</option>
                    {workflow.steps
                      .filter((s) => s.key !== req.current_step && req.amount >= (s.min_amount ?? 0))
                      .map((s) => (
                        <option key={s.key} value={s.key}>
                          {s.label || humanise(s.key)}
                          {s.department ? ` · ${humanise(s.department)}` : ""}
                        </option>
                      ))}
                  </select>
                  <textarea
                    value={routeReason}
                    onChange={(e) => setRouteReason(e.target.value)}
                    rows={2}
                    placeholder="Why it needs to go there — required, and read at audit."
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <button
                    type="button"
                    onClick={handleRoute}
                    disabled={routeBusy || !routeTarget || routeReason.trim() === ""}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {routeBusy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <ArrowLeftRight className="h-3.5 w-3.5" />
                    )}
                    Move it
                  </button>
                </div>
                {routeError ? (
                  <p className="mt-2 text-xs text-red-700">{routeError}</p>
                ) : null}
              </Card>
            ) : null}

            {/* Escalate / delegate outward. Only offered while the request is
                actually sitting at a step — there is nothing to sign off
                otherwise, and offering it would be a dead end. */}
            {req.status === "in_review" && req.current_step ? (
              <Card
                title="Send for sign-off"
                subtitle="Email a secure link — works for someone with no DOCex account"
              >
                <p className="text-xs text-gray-500">
                  For the {humanise(req.current_step)} step. The link expires in seven days,
                  works only for that address, and the decision is recorded against their
                  email with the time and IP. A blocking check still can&rsquo;t be released
                  this way.
                </p>
                <div className="mt-3 space-y-2">
                  <input
                    type="email"
                    value={signoffEmail}
                    onChange={(e) => setSignoffEmail(e.target.value)}
                    placeholder="approver@organisation.org"
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <input
                    value={signoffNote}
                    onChange={(e) => setSignoffNote(e.target.value)}
                    placeholder="Note (optional) — why you're sending it to them"
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  />
                  <button
                    type="button"
                    onClick={sendForSignoff}
                    disabled={signoffBusy || signoffEmail.trim() === ""}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {signoffBusy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5" />
                    )}
                    Send link
                  </button>
                </div>

                {signoffError ? (
                  <p className="mt-2 text-xs text-red-700">{signoffError}</p>
                ) : null}

                {signoffResult ? (
                  <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <p className="text-xs font-medium text-gray-900">
                      {signoffResult.sent
                        ? `Emailed to ${signoffResult.approver_email}.`
                        : `Link created for ${signoffResult.approver_email} — email isn't configured on this instance, so send it yourself.`}
                    </p>
                    {/* Always shown, not only when the email failed: the
                        sender may want to paste it into WhatsApp, which is
                        how a lot of this actually gets chased. */}
                    <div className="mt-2 flex items-center gap-2">
                      <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 text-[11px] text-gray-600 ring-1 ring-gray-200">
                        {signoffResult.link}
                      </code>
                      <button
                        type="button"
                        onClick={() => {
                          void navigator.clipboard?.writeText(signoffResult.link);
                          setLinkCopied(true);
                        }}
                        className="shrink-0 rounded-md border border-gray-300 bg-white px-2 py-1 text-[11px] font-medium text-gray-700 transition hover:bg-gray-50"
                      >
                        {linkCopied ? "Copied" : "Copy"}
                      </button>
                    </div>
                  </div>
                ) : null}
              </Card>
            ) : null}

            <Card title="Comments" subtitle="Anyone who can see this requisition can comment on it">
              {req.comments.length === 0 ? (
                <p className="text-sm text-gray-500">No comments yet.</p>
              ) : (
                <ol className="space-y-3">
                  {req.comments.map((c) => (
                    <li key={c.id} className="border-l-2 border-gray-200 pl-3">
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <MessageSquare className="h-3 w-3 text-gray-400" />
                        <span className="font-medium text-gray-900">{c.author}</span>
                        {c.department ? <span>· {humanise(c.department)}</span> : null}
                        <span className="text-gray-400">· {dateTime(c.at)}</span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-gray-800">{c.text}</p>
                    </li>
                  ))}
                </ol>
              )}
              <div className="mt-4 border-t border-gray-100 pt-3">
                <textarea
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  rows={2}
                  placeholder="Add a comment…"
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                <button
                  type="button"
                  onClick={postComment}
                  disabled={commentBusy || !commentText.trim()}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {commentBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                  Comment
                </button>
                {commentError ? <p className="mt-2 text-xs text-red-700">{commentError}</p> : null}
              </div>
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

// ─── the approval route ─────────────────────────────────────────────────────

/**
 * Every stage of the org's chain for this amount, in order, each showing the
 * department that owns it and what has happened there.
 *
 * Four states a stage can be in, and each is shown differently because they
 * mean different things to whoever is reading:
 *
 *   done         someone decided — named, dated, and with what they decided
 *   current      it is sitting here now, waiting on this department
 *   upcoming     it will reach here next
 *   not required this step does not engage at this amount
 *
 * The last one earns its place: silently hiding a step that did not engage
 * makes "why did this never reach the ED?" unanswerable from the record,
 * and that is exactly the kind of question an auditor asks months later.
 */
function ApprovalRoute({
  req,
  workflow,
}: {
  req: Requisition;
  workflow: RequisitionWorkflow;
}) {
  if (!workflow.steps.length) {
    return (
      <p className="text-sm text-gray-500">
        No approval chain is configured for this organisation, so requisitions are
        approved on submission. Set one under Org settings.
      </p>
    );
  }

  // The last decision recorded at each step — a step can be decided more than
  // once if a requisition was returned and resubmitted, and the latest is the
  // one that describes where things stand.
  const lastAt = new Map<string, (typeof req.approvals)[number]>();
  for (const a of req.approvals) lastAt.set(a.step, a);

  const engagedKeys = workflow.steps
    .filter((s) => req.amount >= (s.min_amount ?? 0))
    .map((s) => s.key);
  const currentIndex = req.current_step ? engagedKeys.indexOf(req.current_step) : -1;

  return (
    <ol className="space-y-0">
      {workflow.steps.map((step, i) => {
        const engaged = req.amount >= (step.min_amount ?? 0);
        const decision = lastAt.get(step.key);
        const isCurrent = req.current_step === step.key;
        const position = engagedKeys.indexOf(step.key);
        const isUpcoming =
          engaged && !decision && !isCurrent && currentIndex >= 0 && position > currentIndex;
        // Passed over: the requisition is now BEYOND this stage and nobody
        // ever decided it — which happens when someone escalated straight
        // past it. Showing this is the whole point of recording the skip;
        // a stage that was silently bypassed is the thing an auditor is
        // looking for, so it must not look identical to one still to come.
        const isSkipped =
          engaged && !decision && !isCurrent && currentIndex >= 0 && position < currentIndex;
        const isLast = i === workflow.steps.length - 1;

        const dot = !engaged
          ? "border-gray-200 bg-white"
          : decision?.decision === "approved"
            ? "border-emerald-500 bg-emerald-500"
            : decision?.decision === "declined"
              ? "border-red-500 bg-red-500"
              : decision?.decision === "returned"
                ? "border-orange-400 bg-orange-400"
                : isCurrent
                  ? "border-brand-600 bg-white ring-4 ring-brand-100"
                  : isSkipped
                    ? "border-amber-400 bg-white"
                    : "border-gray-300 bg-white";

        return (
          <li key={step.key} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`mt-1 h-3 w-3 shrink-0 rounded-full border-2 ${dot}`} />
              {!isLast ? <span className="my-0.5 w-px flex-1 bg-gray-200" /> : null}
            </div>
            <div className={`min-w-0 flex-1 ${isLast ? "pb-0" : "pb-4"}`}>
              <div className="flex flex-wrap items-center gap-x-2">
                <span
                  className={
                    engaged ? "text-sm font-medium text-gray-900" : "text-sm text-gray-400"
                  }
                >
                  {step.label || humanise(step.key)}
                </span>
                {isCurrent ? (
                  <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700 ring-1 ring-brand-200">
                    Waiting here now
                  </span>
                ) : null}
                {isSkipped ? (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
                    Skipped
                  </span>
                ) : null}
                {decision ? (
                  <span
                    className={
                      decision.decision === "approved"
                        ? "text-[11px] font-semibold text-emerald-700"
                        : decision.decision === "declined"
                          ? "text-[11px] font-semibold text-red-700"
                          : "text-[11px] font-semibold text-orange-700"
                    }
                  >
                    {humanise(decision.decision)}
                  </span>
                ) : null}
              </div>

              {/* Who owns this stage — the question this card exists for. */}
              <p className={engaged ? "text-xs text-gray-600" : "text-xs text-gray-400"}>
                {step.department ? humanise(step.department) : "No department assigned"}
                {step.can_override ? " · may release a blocking check" : ""}
              </p>

              {decision ? (
                <p className="mt-0.5 text-xs text-gray-500">
                  {decision.actor} · {dateTime(decision.at)}
                </p>
              ) : !engaged ? (
                <p className="mt-0.5 text-xs text-gray-400">
                  Not required at {money(req.amount, req.currency)} — engages from{" "}
                  {money(step.min_amount, req.currency)}
                </p>
              ) : isUpcoming ? (
                <p className="mt-0.5 text-xs text-gray-400">Next after the current step</p>
              ) : isSkipped ? (
                <p className="mt-0.5 text-xs text-amber-700">
                  Passed over without a decision — see the audit log for who moved it and why
                </p>
              ) : isCurrent ? (
                <p className="mt-0.5 text-xs text-gray-500">
                  {req.status === "on_hold"
                    ? "On hold — still owned by this department"
                    : "Awaiting a decision from this department"}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Who was copied on this requisition, and why. Informed, never asked to act. */
function CopiedCard({
  req,
  workflow,
}: {
  req: Requisition;
  workflow: RequisitionWorkflow;
}) {
  // Mirrors requisitions.cc_recipients() exactly: every matching rule fires,
  // because being copied is additive rather than a ladder.
  const rules = workflow.cc_rules.filter(
    (r) => (r.department || r.emails.length) && req.amount >= r.min_amount,
  );
  if (!rules.length) return null;

  return (
    <Card
      title="Copied on this request"
      subtitle="Notified when it was raised — informed, never asked to approve"
    >
      <ul className="space-y-2">
        {rules.map((r, i) => (
          <li key={`${r.min_amount}-${i}`} className="text-sm">
            <span className="font-medium text-gray-900">
              {r.label || humanise(r.department) || "Named recipients"}
            </span>
            {r.department ? (
              <span className="text-gray-600"> · {humanise(r.department)} department</span>
            ) : null}
            {r.emails.length ? (
              <p className="text-xs text-gray-600">{r.emails.join(", ")}</p>
            ) : null}
            <p className="text-xs text-gray-400">
              Copied because this is at or above {money(r.min_amount, req.currency)}
            </p>
          </li>
        ))}
      </ul>
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

const _COMPLIANCE_VERDICT_STYLE: Record<string, string> = {
  approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
  not_applicable: "bg-gray-50 text-gray-500 border-gray-200",
  flagged: "bg-amber-50 text-amber-700 border-amber-200",
  flag: "bg-amber-50 text-amber-700 border-amber-200",
  insufficient_evidence: "bg-amber-50 text-amber-700 border-amber-200",
  blocked: "bg-red-50 text-red-700 border-red-200",
  block: "bg-red-50 text-red-700 border-red-200",
};

function ComplianceVerdictBadge({
  verdict,
  compact,
}: {
  verdict: string;
  compact?: boolean;
}) {
  const style = _COMPLIANCE_VERDICT_STYLE[verdict] ?? "bg-gray-50 text-gray-600 border-gray-200";
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 font-medium ${style} ${
        compact ? "text-[11px]" : "text-xs"
      }`}
    >
      {humanise(verdict)}
    </span>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
