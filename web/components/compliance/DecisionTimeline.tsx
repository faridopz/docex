"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Loader2,
  MessageSquarePlus,
  Reply,
  Send,
  Sparkles,
  UserPlus,
} from "lucide-react";
import {
  addCheckNote,
  escalateCheck,
  requestClarification,
  respondToClarification,
} from "@/lib/api";
import type {
  ComplianceCheckResult,
  DecisionEvent,
  DecisionEventType,
} from "@/types";
import { decisionEventColor, decisionEventLabel } from "@/types";
import { SignaturePad } from "./SignaturePad";

/**
 * <DecisionTimeline>
 *
 * The human-decision audit trail. Renders the append-only `decision_log`
 * of a compliance check as a vertical timeline with: timestamps · event
 * type chip · note · optional rule reference. Below the timeline sits a
 * compact "Add note" form so the officer can record context without
 * leaving the page.
 *
 * Why this exists: the system-side audit trail (rulebook snapshot,
 * verdict, citations) tells auditors WHAT was flagged. The decision log
 * tells them WHAT THE TEAM DID about it. Auditors care about the second
 * one — and until now, DOCex didn't capture it.
 *
 * The component manages its own state for the note-input form. When a
 * note is added, it calls back via onUpdate so the parent page can swap
 * in the updated check (with the new event appended).
 */
export function DecisionTimeline({
  check,
  onUpdate,
}: {
  check: ComplianceCheckResult;
  onUpdate: (updated: ComplianceCheckResult) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const events = check.decision_log ?? [];

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 hover:bg-gray-50/60"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-100 text-gray-600">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="text-left">
            <p className="text-sm font-semibold text-gray-900">Decision log</p>
            <p className="text-xs text-gray-500">
              {events.length}{" "}
              {events.length === 1 ? "event" : "events"} · append-only audit trail
            </p>
          </div>
        </div>
        {collapsed ? (
          <ChevronRight className="h-4 w-4 text-gray-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-gray-400" />
        )}
      </button>

      {!collapsed && (
        <div className="border-t border-gray-100 px-5 py-5">
          {events.length === 0 ? (
            <p className="text-sm text-gray-500">
              No events yet — events get logged automatically as your team
              acts on this check.
            </p>
          ) : (
            <ol className="relative ml-3 space-y-5 border-l border-gray-200 pl-5">
              {events.map((e, i) => (
                <TimelineEvent key={i} event={e} />
              ))}
            </ol>
          )}

          <AddNoteForm
            checkId={check.payment_id}
            onAdded={onUpdate}
            existingRuleIds={check.results.map((r) => ({
              id: r.rule_id,
              label: r.rule_description,
            }))}
          />

          <ApprovalChainPanel check={check} onUpdate={onUpdate} />
        </div>
      )}
    </div>
  );
}

/* ─── One event in the timeline ────────────────────────────────────────── */

function TimelineEvent({ event }: { event: DecisionEvent }) {
  const dot = dotColor(event.type);
  return (
    <li className="relative">
      <span
        className={`absolute -left-[27px] top-1 flex h-3 w-3 items-center justify-center rounded-full ring-2 ring-white ${dot}`}
        aria-hidden
      />
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${decisionEventColor[event.type]}`}
        >
          {decisionEventLabel[event.type]}
        </span>
        <time
          className="text-[11px] text-gray-400"
          dateTime={event.timestamp}
          title={new Date(event.timestamp).toLocaleString()}
        >
          {formatRelative(new Date(event.timestamp))}
        </time>
        {event.actor && (
          <span className="text-[11px] text-gray-500">· {event.actor}</span>
        )}
      </div>
      {event.note && (
        <p className="mt-1 text-sm leading-relaxed text-gray-700">
          {event.note}
        </p>
      )}
      {event.rule_description && (
        <p
          className="mt-1 truncate text-[11px] text-gray-500"
          title={event.rule_description}
        >
          <span className="font-medium">Rule:</span> {event.rule_description}
        </p>
      )}
      {(event.signature_data_url || event.signed_name) && (
        <div className="mt-2 flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50/60 p-2">
          {event.signature_data_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={event.signature_data_url}
              alt={
                event.signed_name
                  ? `Signature of ${event.signed_name}`
                  : "Signature"
              }
              className="h-10 w-28 rounded-md border border-gray-200 bg-white object-contain"
            />
          )}
          {event.signed_name && (
            <div className="leading-tight">
              <p className="text-[10px] uppercase tracking-wide text-gray-400">
                Signed by
              </p>
              <p className="text-xs font-medium text-gray-700">
                {event.signed_name}
              </p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/* ─── Add note form ────────────────────────────────────────────────────── */

function AddNoteForm({
  checkId,
  onAdded,
  existingRuleIds,
}: {
  checkId: string;
  onAdded: (updated: ComplianceCheckResult) => void;
  existingRuleIds: { id: string; label: string }[];
}) {
  const [note, setNote] = useState("");
  const [ruleId, setRuleId] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const trimmed = note.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await addCheckNote(
        checkId,
        trimmed,
        ruleId || undefined,
      );
      onAdded(updated);
      setNote("");
      setRuleId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the note.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="mt-6 rounded-xl border border-gray-200 bg-gray-50/40 p-4"
    >
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-gray-600">
        <MessageSquarePlus className="h-3.5 w-3.5" />
        Add a note
      </div>
      <p className="mt-1 text-[11px] text-gray-500">
        Free-text context that gets timestamped onto the decision log.
        Optionally tag it to a specific rule.
      </p>

      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={2}
        placeholder="e.g. 'Confirmed via email with vendor on 28/05 — CAC is in renewal, approved per finance director.'"
        className="mt-3 w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {existingRuleIds.length > 0 && (
          <select
            value={ruleId}
            onChange={(e) => setRuleId(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs focus:border-brand-500 focus:outline-none"
          >
            <option value="">Not tied to a specific rule</option>
            {existingRuleIds.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label.length > 60
                  ? r.label.slice(0, 60) + "…"
                  : r.label}
              </option>
            ))}
          </select>
        )}

        <button
          type="submit"
          disabled={!note.trim() || submitting}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
        >
          {submitting ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Send className="h-3.5 w-3.5" />
              Add to log
            </>
          )}
        </button>
      </div>

      {error && (
        <p className="mt-2 text-[11px] text-rose-600">{error}</p>
      )}
      <p className="mt-2 text-[10px] text-gray-400">
        Tip: ⌘+Enter to submit. Notes are permanent — they become part of
        the audit trail.
      </p>
    </form>
  );
}

/* ─── Helpers ──────────────────────────────────────────────────────────── */

function dotColor(type: DecisionEventType): string {
  switch (type) {
    case "check_run":
      return "bg-gray-400";
    case "note_added":
      return "bg-sky-500";
    case "rule_dismissed":
      return "bg-amber-500";
    case "rule_escalated":
      return "bg-violet-500";
    case "clarification_requested":
      return "bg-blue-500";
    case "clarification_received":
      return "bg-indigo-500";
    case "escalated":
      return "bg-violet-500";
    case "approved":
      return "bg-emerald-500";
    case "unapproved":
      return "bg-rose-500";
    default:
      return "bg-gray-400";
  }
}

/* ─── Approval-chain panel ──────────────────────────────────────────────
 *
 * Three actions a compliance officer can take from the check page:
 *
 *   1. Escalate → hand the whole check to a named reviewer. Sets
 *      pending_with and (optionally) signs the handoff.
 *   2. Request clarification → ask a SPECIFIC question, tied to a
 *      SPECIFIC person, optionally about a SPECIFIC rule. Replaces the
 *      ad-hoc email back-and-forth.
 *   3. Respond to a pending clarification → only shown when
 *      pending_question is set. Clears the question and logs the
 *      response.
 *
 * Each action expands inline so the officer doesn't lose context — no
 * modals, no page navigation. Signatures are optional, but the field
 * is always there so it's available when the org's policy requires one.
 */
function ApprovalChainPanel({
  check,
  onUpdate,
}: {
  check: ComplianceCheckResult;
  onUpdate: (updated: ComplianceCheckResult) => void;
}) {
  type Mode = "idle" | "escalate" | "clarify" | "respond";
  const [mode, setMode] = useState<Mode>("idle");

  const hasOpenQuestion = Boolean(check.pending_question);

  return (
    <div className="mt-6 rounded-xl border border-gray-200 bg-white">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">
          Approval chain
        </span>
        {check.pending_with && (
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200">
            Sitting with {check.pending_with}
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <ChipButton
            onClick={() => setMode(mode === "escalate" ? "idle" : "escalate")}
            active={mode === "escalate"}
            icon={<UserPlus className="h-3.5 w-3.5" />}
          >
            Escalate
          </ChipButton>
          <ChipButton
            onClick={() => setMode(mode === "clarify" ? "idle" : "clarify")}
            active={mode === "clarify"}
            icon={<HelpCircle className="h-3.5 w-3.5" />}
          >
            Request clarification
          </ChipButton>
          {hasOpenQuestion && (
            <ChipButton
              onClick={() => setMode(mode === "respond" ? "idle" : "respond")}
              active={mode === "respond"}
              icon={<Reply className="h-3.5 w-3.5" />}
            >
              Respond
            </ChipButton>
          )}
        </div>
      </div>

      {check.pending_question && (
        <div className="border-t border-gray-100 bg-blue-50/40 px-4 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-blue-700">
            Outstanding question for {check.pending_with || "reviewer"}
          </p>
          <p className="mt-0.5 text-sm text-gray-800">
            {check.pending_question}
          </p>
        </div>
      )}

      {mode === "escalate" && (
        <EscalateForm
          checkId={check.payment_id}
          onDone={(c) => {
            setMode("idle");
            onUpdate(c);
          }}
          onCancel={() => setMode("idle")}
        />
      )}
      {mode === "clarify" && (
        <ClarifyForm
          checkId={check.payment_id}
          rules={check.results.map((r) => ({
            id: r.rule_id,
            label: r.rule_description,
          }))}
          onDone={(c) => {
            setMode("idle");
            onUpdate(c);
          }}
          onCancel={() => setMode("idle")}
        />
      )}
      {mode === "respond" && (
        <RespondForm
          checkId={check.payment_id}
          onDone={(c) => {
            setMode("idle");
            onUpdate(c);
          }}
          onCancel={() => setMode("idle")}
        />
      )}
    </div>
  );
}

function ChipButton({
  children,
  onClick,
  active,
  icon,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active: boolean;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition " +
        (active
          ? "border-brand-300 bg-brand-50 text-brand-700"
          : "border-gray-200 bg-white text-gray-600 hover:border-brand-300 hover:text-brand-700")
      }
    >
      {icon}
      {children}
    </button>
  );
}

/* ─── Escalate form ────────────────────────────────────────────────────── */

function EscalateForm({
  checkId,
  onDone,
  onCancel,
}: {
  checkId: string;
  onDone: (updated: ComplianceCheckResult) => void;
  onCancel: () => void;
}) {
  const [pendingWith, setPendingWith] = useState("");
  const [reason, setReason] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!pendingWith.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await escalateCheck(checkId, {
        pending_with: pendingWith.trim(),
        reason: reason.trim() || undefined,
        signature_data_url: sig,
        signed_name: name.trim() || null,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not escalate.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ActionForm
      title="Escalate to a reviewer"
      onSubmit={submit}
      onCancel={onCancel}
      submitLabel="Escalate"
      submitting={submitting}
      disabled={!pendingWith.trim()}
      error={error}
    >
      <LabelledInput
        label="Hand off to"
        value={pendingWith}
        onChange={setPendingWith}
        placeholder="e.g. Finance Director, abosede@taconnect.org"
        required
      />
      <LabelledTextarea
        label="Why are you escalating? (optional)"
        value={reason}
        onChange={setReason}
        placeholder="Quick context for the reviewer."
      />
      <SignaturePad
        name={name}
        onNameChange={setName}
        dataUrl={sig}
        onChange={setSig}
        label="Sign the handoff (optional)"
        hint="Signing makes the handoff explicit on the audit trail. Skip if your policy doesn't require it."
      />
    </ActionForm>
  );
}

/* ─── Clarify form ─────────────────────────────────────────────────────── */

function ClarifyForm({
  checkId,
  rules,
  onDone,
  onCancel,
}: {
  checkId: string;
  rules: { id: string; label: string }[];
  onDone: (updated: ComplianceCheckResult) => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [pendingWith, setPendingWith] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!question.trim() || !pendingWith.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await requestClarification(checkId, {
        question: question.trim(),
        pending_with: pendingWith.trim(),
        rule_id: ruleId || null,
        signature_data_url: sig,
        signed_name: name.trim() || null,
      });
      onDone(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not send the question.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ActionForm
      title="Request clarification"
      onSubmit={submit}
      onCancel={onCancel}
      submitLabel="Send question"
      submitting={submitting}
      disabled={!question.trim() || !pendingWith.trim()}
      error={error}
    >
      <LabelledTextarea
        label="What do you need to know?"
        value={question}
        onChange={setQuestion}
        placeholder="e.g. 'CAC is missing from the vendor file. Can you upload the renewal cert or confirm it's in progress?'"
        required
      />
      <LabelledInput
        label="Ask who?"
        value={pendingWith}
        onChange={setPendingWith}
        placeholder="e.g. tunde@vendor.com, Finance officer"
        required
      />
      {rules.length > 0 && (
        <label className="block">
          <span className="text-[11px] font-medium uppercase tracking-wide text-gray-600">
            Tie to a rule (optional)
          </span>
          <select
            value={ruleId}
            onChange={(e) => setRuleId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
          >
            <option value="">Not tied to a specific rule</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label.length > 80 ? r.label.slice(0, 80) + "…" : r.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <SignaturePad
        name={name}
        onNameChange={setName}
        dataUrl={sig}
        onChange={setSig}
        label="Sign the request (optional)"
        hint="Identifies you as the officer who raised this clarification."
      />
    </ActionForm>
  );
}

/* ─── Respond form ─────────────────────────────────────────────────────── */

function RespondForm({
  checkId,
  onDone,
  onCancel,
}: {
  checkId: string;
  onDone: (updated: ComplianceCheckResult) => void;
  onCancel: () => void;
}) {
  const [response, setResponse] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!response.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await respondToClarification(checkId, {
        response: response.trim(),
        signature_data_url: sig,
        signed_name: name.trim() || null,
      });
      onDone(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save the response.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ActionForm
      title="Respond to clarification"
      onSubmit={submit}
      onCancel={onCancel}
      submitLabel="Send response"
      submitting={submitting}
      disabled={!response.trim()}
      error={error}
    >
      <LabelledTextarea
        label="Your response"
        value={response}
        onChange={setResponse}
        placeholder="e.g. 'CAC renewal cert is now uploaded — see attachments. Renewal completed 02/06.'"
        required
      />
      <SignaturePad
        name={name}
        onNameChange={setName}
        dataUrl={sig}
        onChange={setSig}
        label="Sign your response (optional)"
        hint="Adds your signature + name to the audit trail beside the response."
      />
    </ActionForm>
  );
}

/* ─── Form scaffolding ─────────────────────────────────────────────────── */

function ActionForm({
  title,
  children,
  onSubmit,
  onCancel,
  submitLabel,
  submitting,
  disabled,
  error,
}: {
  title: string;
  children: React.ReactNode;
  onSubmit: () => void;
  onCancel: () => void;
  submitLabel: string;
  submitting: boolean;
  disabled: boolean;
  error: string | null;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-3 border-t border-gray-100 bg-gray-50/40 px-4 py-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-600">
        {title}
      </p>
      {children}
      {error && <p className="text-[11px] text-rose-600">{error}</p>}
      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-300"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || disabled}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
        >
          {submitting ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Send className="h-3.5 w-3.5" />
              {submitLabel}
            </>
          )}
        </button>
      </div>
    </form>
  );
}

function LabelledInput({
  label,
  value,
  onChange,
  placeholder,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium uppercase tracking-wide text-gray-600">
        {label} {required && <span className="text-rose-500">*</span>}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
    </label>
  );
}

function LabelledTextarea({
  label,
  value,
  onChange,
  placeholder,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium uppercase tracking-wide text-gray-600">
        {label} {required && <span className="text-rose-500">*</span>}
      </span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={2}
        className="mt-1 w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
    </label>
  );
}

function formatRelative(d: Date): string {
  const diff = Date.now() - d.getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d ago`;
  return d.toLocaleDateString();
}
