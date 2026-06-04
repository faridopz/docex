"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  FileText,
  Loader2,
  Mail,
  Pencil,
  Play,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { GuidanceCard } from "@/components/GuidanceCard";
import {
  deleteRulebook,
  getRulebook,
  updateRulebook,
} from "@/lib/api";
import {
  categoryColor,
  categoryLabel,
  type NotificationTrigger,
  type PolicyRule,
  type PolicyRulebook,
  type RuleCategory,
} from "@/types";

/**
 * Rulebook editor.
 *
 * The compliance officer's main workbench. Shows every rule Claude
 * extracted from the policy, grouped by category, with an active toggle
 * and an inline description editor.
 *
 * v1 scope (this page):
 *   - View all rules grouped by category, with category counts
 *   - Toggle each rule active/inactive (the most common edit)
 *   - Edit a rule's description inline (the second most common edit —
 *     correcting Claude's interpretation of an ambiguous clause)
 *   - Delete a rule (rare but necessary)
 *   - Rename the rulebook inline
 *   - Save the whole rulebook back to the API as one PUT
 *   - Show interpretation_notes as an amber banner at the top so any
 *     ambiguity Claude flagged is the first thing the officer sees
 *
 * Deferred to v2 (when the officer asks for it):
 *   - Editing condition, evidence_required, category inline
 *   - Adding a new rule from scratch
 *   - Reordering rules within a category
 *
 * UX choices worth noting:
 *   - Sticky save bar at the bottom whenever there are unsaved changes,
 *     so the user can't accidentally navigate away. Goal-gradient — the
 *     bar shows a count of unsaved edits ("3 changes") to make progress
 *     visible.
 *   - Active toggle uses emerald-when-on, gray-when-off — matches the
 *     extraction confidence palette so the visual language is consistent.
 *   - The "Run a check" CTA in the header is the dominant action.
 *     Editing is something they do once and rarely return to; running
 *     checks is the day-to-day work.
 */

export default function RulebookEditorPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;

  const [original, setOriginal] = useState<PolicyRulebook | null>(null);
  const [draft, setDraft] = useState<PolicyRulebook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notesDismissed, setNotesDismissed] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Load on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rb = await getRulebook(id);
        if (!cancelled) {
          setOriginal(rb);
          setDraft(structuredClone(rb));
        }
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load this rulebook.",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Compute dirty state by comparing the editable bits of draft vs original
  const dirty = useMemo(() => {
    if (!original || !draft) return false;
    if (original.name !== draft.name) return true;
    if ((original.notification_email ?? "") !== (draft.notification_email ?? ""))
      return true;
    if (
      (original.notification_trigger ?? "") !==
      (draft.notification_trigger ?? "")
    )
      return true;
    if (original.rules.length !== draft.rules.length) return true;
    return original.rules.some((r, i) => {
      const d = draft.rules[i];
      if (!d) return true;
      return (
        r.id !== d.id ||
        r.description !== d.description ||
        r.active !== d.active
      );
    });
  }, [original, draft]);

  const changeCount = useMemo(() => {
    if (!original || !draft) return 0;
    let n = 0;
    if (original.name !== draft.name) n++;
    if ((original.notification_email ?? "") !== (draft.notification_email ?? ""))
      n++;
    if (
      (original.notification_trigger ?? "") !==
      (draft.notification_trigger ?? "")
    )
      n++;
    // Rules removed
    const draftIds = new Set(draft.rules.map((r) => r.id));
    n += original.rules.filter((r) => !draftIds.has(r.id)).length;
    // Rules edited (description or active changed)
    for (const r of draft.rules) {
      const o = original.rules.find((x) => x.id === r.id);
      if (!o) continue;
      if (o.description !== r.description) n++;
      if (o.active !== r.active) n++;
    }
    return n;
  }, [original, draft]);

  // Group active rules by category for visual chunking
  const groupedRules = useMemo(() => {
    if (!draft) return [] as { category: RuleCategory; rules: PolicyRule[] }[];
    const groups = new Map<RuleCategory, PolicyRule[]>();
    for (const r of draft.rules) {
      const cat = (r.category ?? "general") as RuleCategory;
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat)!.push(r);
    }
    // Keep a deterministic category order so the user finds things consistently
    const order: RuleCategory[] = [
      "procurement",
      "receipts",
      "approvals",
      "vendor",
      "advance",
      "retirement",
      "documentation",
      "general",
    ];
    return order
      .filter((c) => groups.has(c))
      .map((category) => ({ category, rules: groups.get(category)! }));
  }, [draft]);

  function updateRule(ruleId: string, patch: Partial<PolicyRule>) {
    setDraft((d) =>
      d
        ? {
            ...d,
            rules: d.rules.map((r) => (r.id === ruleId ? { ...r, ...patch } : r)),
          }
        : d,
    );
  }

  function removeRule(ruleId: string) {
    setDraft((d) =>
      d ? { ...d, rules: d.rules.filter((r) => r.id !== ruleId) } : d,
    );
  }

  async function handleSave() {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await updateRulebook(draft.id, {
        name: draft.name,
        rules: draft.rules,
        interpretation_notes: draft.interpretation_notes,
        notification_email: draft.notification_email,
        notification_trigger: draft.notification_trigger,
      });
      setOriginal(saved);
      setDraft(structuredClone(saved));
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Could not save your changes.",
      );
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    if (!original) return;
    setDraft(structuredClone(original));
  }

  async function handleDelete() {
    if (!draft) return;
    try {
      await deleteRulebook(draft.id);
      // Bounce back to the list — using window.location to ensure a full
      // re-fetch of the list so the deleted rulebook is gone from view.
      window.location.href = "/compliance";
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Could not delete this rulebook.",
      );
      setConfirmingDelete(false);
    }
  }

  if (error) {
    return <LoadFailedScreen error={error} />;
  }
  if (!draft) {
    return <LoadingScreen />;
  }

  const hasNotes = !!draft.interpretation_notes && !notesDismissed;

  return (
    <div className="min-h-screen bg-gray-50 pb-32">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between gap-4 px-6">
          <Link
            href="/compliance"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <ShieldCheck className="h-4 w-4 text-brand-600" />
            Rulebook editor
          </span>
          <Link
            href={`/compliance/rulebooks/${draft.id}/check`}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
            title="Run a compliance check against this rulebook"
          >
            <Play className="h-3.5 w-3.5" />
            Run a check
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        {/* Title / rename */}
        <div className="space-y-2">
          {editingName ? (
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              onBlur={() => setEditingName(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter") setEditingName(false);
                if (e.key === "Escape") {
                  if (original) setDraft({ ...draft, name: original.name });
                  setEditingName(false);
                }
              }}
              autoFocus
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-2xl font-bold text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          ) : (
            <button
              type="button"
              onClick={() => setEditingName(true)}
              className="group flex items-center gap-2 text-left text-3xl font-bold tracking-tight text-gray-900"
              title="Click to rename"
            >
              {draft.name}
              <Pencil className="h-4 w-4 text-gray-300 transition-colors group-hover:text-gray-500" />
            </button>
          )}
          <p className="flex items-center gap-1.5 text-xs text-gray-500">
            <FileText className="h-3 w-3" />
            {draft.source_documents.length === 1
              ? draft.source_documents[0]
              : `${draft.source_documents.length} source documents`}
          </p>
        </div>

        {/* Interpretation notes banner */}
        {hasNotes && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="flex-1 space-y-1 text-sm text-amber-900">
              <p className="font-medium">DOCex flagged some clauses for your review</p>
              <p className="whitespace-pre-wrap leading-relaxed text-amber-800">
                {draft.interpretation_notes}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setNotesDismissed(true)}
              className="shrink-0 text-amber-600 hover:text-amber-900"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <GuidanceCard title="Review and edit before running checks">
          DOCex extracted every rule it found. Toggle off any rule you don't
          want checked, edit a description if it was misread, or delete
          a rule entirely. The source quote on each card is the exact policy
          text the rule came from.
        </GuidanceCard>

        {/* Notifications — opt-in per rulebook. Different policies often
            route to different people, so the config lives with the
            rulebook, not globally. */}
        <NotificationSettings
          email={draft.notification_email ?? ""}
          trigger={(draft.notification_trigger ?? "") as NotificationTrigger | ""}
          onEmailChange={(email) =>
            setDraft({ ...draft, notification_email: email || null })
          }
          onTriggerChange={(trigger) =>
            setDraft({
              ...draft,
              notification_trigger: trigger || null,
            })
          }
        />

        {/* Summary chips */}
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-emerald-700 ring-1 ring-emerald-200">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {draft.rules.filter((r) => r.active).length} active
          </span>
          {draft.rules.some((r) => !r.active) && (
            <span className="text-xs text-gray-500">
              {draft.rules.filter((r) => !r.active).length} inactive
            </span>
          )}
          <span className="ml-auto text-xs text-gray-400">
            {groupedRules.length}{" "}
            {groupedRules.length === 1 ? "category" : "categories"}
          </span>
        </div>

        {/* Rules grouped by category */}
        <div className="space-y-8">
          {groupedRules.map(({ category, rules }) => (
            <section key={category} className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900">
                  {categoryLabel[category]}
                </h2>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${categoryColor[category]}`}
                >
                  {rules.length} {rules.length === 1 ? "rule" : "rules"}
                </span>
              </div>
              <div className="space-y-3">
                {rules.map((rule) => (
                  <RuleCard
                    key={rule.id}
                    rule={rule}
                    onUpdate={(patch) => updateRule(rule.id, patch)}
                    onRemove={() => removeRule(rule.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>

        {/* Danger zone — small, end of page */}
        <div className="mt-12 border-t border-gray-200 pt-6">
          {confirmingDelete ? (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <span>
                Delete this rulebook? All rules will be permanently removed.
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(false)}
                  className="rounded-md border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 transition hover:bg-rose-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleDelete}
                  className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-rose-700"
                >
                  Delete rulebook
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              className="inline-flex items-center gap-1.5 text-xs text-gray-400 transition hover:text-rose-600"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete this rulebook
            </button>
          )}
        </div>
      </main>

      {/* Sticky save bar */}
      {dirty && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white shadow-[0_-4px_12px_0_rgb(0_0_0/0.04)]">
          <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-6 py-3">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-2 w-2 rounded-full bg-amber-400" />
              <span className="text-sm font-medium text-gray-900">
                {changeCount} unsaved{" "}
                {changeCount === 1 ? "change" : "changes"}
              </span>
              {saveError && (
                <span className="text-xs text-rose-600">· {saveError}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleDiscard}
                disabled={saving}
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-gray-300 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Discard
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4" />
                    Save changes
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Notification settings card ──────────────────────────────────────── */

const TRIGGER_OPTIONS: { value: NotificationTrigger | ""; label: string; hint: string }[] = [
  { value: "", label: "Don't send", hint: "No emails — review checks in DOCex" },
  {
    value: "blocked_only",
    label: "Only when blocked",
    hint: "Email only for clear policy violations",
  },
  {
    value: "flagged_or_blocked",
    label: "Flagged or blocked",
    hint: "Recommended — covers anything that needs review",
  },
  { value: "always", label: "Every check", hint: "Email after every check, even passes" },
];

function NotificationSettings({
  email,
  trigger,
  onEmailChange,
  onTriggerChange,
}: {
  email: string;
  trigger: NotificationTrigger | "";
  onEmailChange: (email: string) => void;
  onTriggerChange: (trigger: NotificationTrigger | "") => void;
}) {
  const enabled = trigger !== "";

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex items-start gap-3">
        <Mail className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
        <div className="flex-1 space-y-1">
          <h3 className="text-base font-semibold text-gray-900">
            Email notifications
          </h3>
          <p className="text-sm text-gray-600">
            Get an alert email after a check against this rulebook completes.
            Different rulebooks can notify different people — procurement to
            the procurement officer, travel policy to the finance manager.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {/* Recipient */}
        <div className="space-y-1.5">
          <label
            htmlFor="notification-email"
            className="block text-xs font-semibold uppercase tracking-wide text-gray-600"
          >
            Send to
          </label>
          <input
            id="notification-email"
            type="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            placeholder="compliance@example.org"
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          />
        </div>

        {/* Trigger */}
        <div className="space-y-1.5">
          <label
            htmlFor="notification-trigger"
            className="block text-xs font-semibold uppercase tracking-wide text-gray-600"
          >
            When to send
          </label>
          <select
            id="notification-trigger"
            value={trigger}
            onChange={(e) =>
              onTriggerChange(e.target.value as NotificationTrigger | "")
            }
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            {TRIGGER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-gray-500">
            {TRIGGER_OPTIONS.find((o) => o.value === trigger)?.hint}
          </p>
        </div>
      </div>

      {enabled && !email && (
        <p className="mt-3 text-xs text-amber-700">
          Add a recipient email above to start sending notifications.
        </p>
      )}
      {enabled && email && (
        <p className="mt-3 text-xs text-gray-500">
          Notifications fire when the backend has SMTP configured (Resend,
          Gmail app password, or your org's SMTP server). Ask your admin
          if you're unsure.
        </p>
      )}
    </section>
  );
}

/* ─── Rule card ───────────────────────────────────────────────────────── */

function RuleCard({
  rule,
  onUpdate,
  onRemove,
}: {
  rule: PolicyRule;
  onUpdate: (patch: Partial<PolicyRule>) => void;
  onRemove: () => void;
}) {
  const [editingDesc, setEditingDesc] = useState(false);
  const [showSource, setShowSource] = useState(false);

  return (
    <div
      className={`rounded-xl border bg-white p-4 transition ${
        rule.active ? "border-gray-200" : "border-gray-100 bg-gray-50/50 opacity-75"
      }`}
    >
      {/* Top row: clause ref + active toggle + delete */}
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {rule.clause_reference && (
            <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[11px] text-gray-600">
              {rule.clause_reference}
            </span>
          )}
          {rule.condition && (
            <span className="text-gray-500" title="When this rule applies">
              when {rule.condition}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ActiveToggle
            active={rule.active}
            onChange={(active) => onUpdate({ active })}
          />
          <button
            type="button"
            onClick={onRemove}
            className="rounded-md p-1 text-gray-300 transition hover:bg-rose-50 hover:text-rose-600"
            aria-label="Delete rule"
            title="Delete this rule"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Description — inline editable */}
      {editingDesc ? (
        <textarea
          value={rule.description}
          onChange={(e) => onUpdate({ description: e.target.value })}
          onBlur={() => setEditingDesc(false)}
          autoFocus
          rows={2}
          className="w-full resize-y rounded-md border border-gray-200 bg-white px-3 py-2 text-sm leading-relaxed text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
        />
      ) : (
        <button
          type="button"
          onClick={() => setEditingDesc(true)}
          className="group block w-full cursor-text text-left text-sm leading-relaxed text-gray-900"
          title="Click to edit"
        >
          {rule.description}
          <Pencil className="ml-1.5 inline h-3 w-3 text-gray-300 transition-colors group-hover:text-gray-500" />
        </button>
      )}

      {/* Evidence required chips */}
      {rule.evidence_required.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {rule.evidence_required.map((ev, i) => (
            <span
              key={i}
              className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600"
            >
              {ev}
            </span>
          ))}
        </div>
      )}

      {/* Source quote */}
      {rule.source_quote && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowSource((s) => !s)}
            className="text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            {showSource ? "Hide source" : "View source quote"}
            {rule.source_page != null && ` · p.${rule.source_page}`}
          </button>
          {showSource && (
            <div className="mt-2 rounded-md border border-gray-100 bg-gray-50 px-3 py-2">
              <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-gray-600">
                {rule.source_quote}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Active toggle (custom switch) ─────────────────────────────────── */

function ActiveToggle({
  active,
  onChange,
}: {
  active: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      onClick={() => onChange(!active)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition ${
        active ? "bg-emerald-500" : "bg-gray-200"
      }`}
      title={active ? "Active — this rule will be checked" : "Inactive — this rule is skipped"}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
          active ? "translate-x-[18px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

/* ─── Loading + error screens ────────────────────────────────────────── */

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading rulebook…
      </div>
    </div>
  );
}

function LoadFailedScreen({ error }: { error: string }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-100 bg-white">
        <div className="mx-auto flex h-16 max-w-4xl items-center px-6">
          <Link
            href="/compliance"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-20">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          <p className="font-medium text-red-900">Could not load this rulebook</p>
          <p className="mt-1">{error}</p>
          <Link
            href="/compliance"
            className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to rulebooks
          </Link>
        </div>
      </main>
    </div>
  );
}
