"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Copy,
  GitCompare,
  Info,
  Layers,
  Pencil,
  Plus,
  Receipt,
  ScanSearch,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  TEMPLATE_CATEGORIES,
  createTemplate,
  deleteTemplate,
  duplicateTemplate,
  isStarter,
  listStarterTemplates,
  listUserTemplates,
  updateTemplate,
  type StoredTemplate,
} from "@/lib/template-store";
import type {
  QuestionTemplate,
  TemplateCategory,
  TemplateQuestion,
} from "@/lib/templates";

const CATEGORY_ICON: Record<TemplateCategory, LucideIcon> = {
  screen: ScanSearch,
  reconcile: GitCompare,
  extract: Receipt,
  compare: Layers,
};

type View = { mode: "list" } | { mode: "create" } | { mode: "edit"; id: string };

export default function TemplatesPage() {
  const starters = listStarterTemplates();
  const [userTemplates, setUserTemplates] = useState<StoredTemplate[]>([]);
  const [view, setView] = useState<View>({ mode: "list" });

  // Load user templates client-side (localStorage) after mount to avoid an
  // SSR/client hydration mismatch.
  useEffect(() => {
    setUserTemplates(listUserTemplates());
  }, []);

  function refresh() {
    setUserTemplates(listUserTemplates());
  }

  function handleUse(id: string) {
    // Navigate to the extraction flow with this template preselected.
    window.location.href = `/app?template=${encodeURIComponent(id)}`;
  }

  function handleDuplicate(id: string) {
    const copy = duplicateTemplate(id);
    refresh();
    if (copy) setView({ mode: "edit", id: copy.id });
  }

  function handleDelete(id: string) {
    if (!confirm("Delete this template? This can't be undone.")) return;
    deleteTemplate(id);
    refresh();
  }

  const editing =
    view.mode === "edit"
      ? userTemplates.find((t) => t.id === view.id) ?? null
      : null;

  return (
    <AppShell
      active="templates"
      actions={
        view.mode === "list" ? (
          <button
            type="button"
            onClick={() => setView({ mode: "create" })}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
          >
            <Plus className="h-3.5 w-3.5" />
            New template
          </button>
        ) : undefined
      }
    >
      <main className="mx-auto max-w-5xl px-6 py-10">
        {view.mode === "list" ? (
          <ListView
            starters={starters}
            userTemplates={userTemplates}
            onCreate={() => setView({ mode: "create" })}
            onUse={handleUse}
            onDuplicate={handleDuplicate}
            onEdit={(id) => setView({ mode: "edit", id })}
            onDelete={handleDelete}
          />
        ) : (
          <TemplateEditor
            initial={editing}
            onCancel={() => setView({ mode: "list" })}
            onSaved={() => {
              refresh();
              setView({ mode: "list" });
            }}
          />
        )}
      </main>
    </AppShell>
  );
}

/* ─── List view ─────────────────────────────────────────────────────────── */

function ListView({
  starters,
  userTemplates,
  onCreate,
  onUse,
  onDuplicate,
  onEdit,
  onDelete,
}: {
  starters: QuestionTemplate[];
  userTemplates: StoredTemplate[];
  onCreate: () => void;
  onUse: (id: string) => void;
  onDuplicate: (id: string) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Template library
        </h1>
        <p className="mt-2 max-w-2xl text-base text-gray-600">
          A template is a reusable set of questions DOCex answers for every
          document you give it — with the source, exact quote, and confidence
          for each answer. Start from one of ours, or build your own.
        </p>
        <div className="mt-3 inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-800">
          <Info className="h-3.5 w-3.5 shrink-0" />
          Your templates are saved to this browser for now. Team-wide sync
          arrives with accounts.
        </div>
      </header>

      {/* Starters */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Start from a template
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {starters.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              actions={
                <>
                  <GhostBtn onClick={() => onDuplicate(t.id)} icon={Copy}>
                    Duplicate
                  </GhostBtn>
                  <PrimaryBtn onClick={() => onUse(t.id)}>Use</PrimaryBtn>
                </>
              }
            />
          ))}
        </div>
      </section>

      {/* User templates */}
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Your templates
          </h2>
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:text-brand-800"
          >
            <Plus className="h-4 w-4" />
            New template
          </button>
        </div>

        {userTemplates.length === 0 ? (
          <button
            type="button"
            onClick={onCreate}
            className="mt-3 flex w-full flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center transition hover:border-brand-300 hover:bg-brand-50/30"
          >
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <Plus className="h-5 w-5" />
            </span>
            <p className="text-sm font-semibold text-gray-900">
              Create your first template
            </p>
            <p className="max-w-md text-xs text-gray-500">
              Define the questions you want answered across a stack of
              documents — applications, invoices, reports, contracts, CVs,
              anything. Reuse it on every batch.
            </p>
          </button>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {userTemplates.map((t) => (
              <TemplateCard
                key={t.id}
                template={t}
                actions={
                  <>
                    <GhostBtn onClick={() => onDelete(t.id)} icon={Trash2}>
                      Delete
                    </GhostBtn>
                    <GhostBtn onClick={() => onDuplicate(t.id)} icon={Copy}>
                      Duplicate
                    </GhostBtn>
                    <GhostBtn onClick={() => onEdit(t.id)} icon={Pencil}>
                      Edit
                    </GhostBtn>
                    <PrimaryBtn onClick={() => onUse(t.id)}>Use</PrimaryBtn>
                  </>
                }
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TemplateCard({
  template,
  actions,
}: {
  template: QuestionTemplate;
  actions: React.ReactNode;
}) {
  const Icon = template.category ? CATEGORY_ICON[template.category] : Layers;
  const cat = TEMPLATE_CATEGORIES.find((c) => c.id === template.category);
  return (
    <div className="flex h-full flex-col rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700 ring-1 ring-amber-100">
          <Icon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold text-gray-900">
              {template.name}
            </h3>
            {isStarter(template.id) && (
              <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">
                Starter
              </span>
            )}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-gray-600">
            {template.description}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
          {template.questions.length} questions
        </span>
        {cat && (
          <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700">
            {cat.label}
          </span>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-gray-100 pt-3">
        {actions}
      </div>
    </div>
  );
}

function PrimaryBtn({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700"
    >
      {children}
      <ArrowRight className="h-3.5 w-3.5" />
    </button>
  );
}

function GhostBtn({
  children,
  onClick,
  icon: Icon,
}: {
  children: React.ReactNode;
  onClick: () => void;
  icon: LucideIcon;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  );
}

/* ─── Editor ────────────────────────────────────────────────────────────── */

function TemplateEditor({
  initial,
  onCancel,
  onSaved,
}: {
  initial: StoredTemplate | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [category, setCategory] = useState<TemplateCategory | "">(
    initial?.category ?? "",
  );
  const [context, setContext] = useState(initial?.defaultContext ?? "");
  const [questions, setQuestions] = useState<TemplateQuestion[]>(
    initial?.questions.length
      ? initial.questions.map((q) => ({ text: q.text, hint: q.hint }))
      : [{ text: "" }],
  );
  const [error, setError] = useState<string | null>(null);

  const validQuestions = questions.filter((q) => q.text.trim().length > 0);
  const canSave = name.trim().length > 0 && validQuestions.length > 0;

  function setQ(i: number, patch: Partial<TemplateQuestion>) {
    setQuestions((qs) => qs.map((q, idx) => (idx === i ? { ...q, ...patch } : q)));
  }
  function addQ() {
    setQuestions((qs) => [...qs, { text: "" }]);
  }
  function removeQ(i: number) {
    setQuestions((qs) => qs.filter((_, idx) => idx !== i));
  }

  function save() {
    if (!canSave) {
      setError("Give the template a name and at least one question.");
      return;
    }
    const input = {
      name,
      description,
      category: category || undefined,
      defaultContext: context,
      questions,
    };
    if (initial) updateTemplate(initial.id, input);
    else createTemplate(input);
    onSaved();
  }

  return (
    <div className="space-y-6">
      <header>
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-gray-500 transition hover:text-gray-800"
        >
          ← Back to library
        </button>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-gray-900">
          {initial ? "Edit template" : "New template"}
        </h1>
      </header>

      <div className="space-y-5 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Vendor contract review"
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </Field>

        <Field label="Description">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="One line on what this template is for."
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </Field>

        <Field label="Category">
          <div className="flex flex-wrap gap-2">
            {TEMPLATE_CATEGORIES.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCategory(category === c.id ? "" : c.id)}
                title={c.blurb}
                className={
                  "rounded-lg border px-3 py-1.5 text-xs font-medium transition " +
                  (category === c.id
                    ? "border-brand-300 bg-brand-50 text-brand-700"
                    : "border-gray-200 bg-white text-gray-600 hover:border-brand-300")
                }
              >
                {c.label}
              </button>
            ))}
          </div>
        </Field>

        <Field
          label="Context (optional)"
          hint="A short paragraph telling DOCex how to interpret these documents — funder priorities, document structure, vocabulary. It sharpens answers; it never scores or ranks."
        >
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            rows={3}
            placeholder="e.g. These are vendor contracts; flag anything that conflicts with our standard payment terms."
            className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </Field>
      </div>

      {/* Questions */}
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Questions</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Each question is answered for every document. Add an optional
              hint to point DOCex at where the answer usually lives — it
              measurably improves accuracy.
            </p>
          </div>
          <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
            {validQuestions.length}
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {questions.map((q, i) => (
            <div
              key={i}
              className="rounded-xl border border-gray-200 bg-gray-50/40 p-3"
            >
              <div className="flex items-start gap-2">
                <span className="mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-200 text-xs font-medium text-gray-600">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                  <input
                    value={q.text}
                    onChange={(e) => setQ(i, { text: e.target.value })}
                    placeholder="Type your question…"
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                  <input
                    value={q.hint ?? ""}
                    onChange={(e) => setQ(i, { hint: e.target.value })}
                    placeholder="Optional hint — where to look, what good looks like"
                    className="w-full rounded-lg border border-dashed border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 placeholder:text-gray-400 focus:border-brand-400 focus:outline-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeQ(i)}
                  className="mt-1 shrink-0 rounded-md p-1.5 text-gray-400 transition hover:bg-rose-50 hover:text-rose-600"
                  aria-label={`Remove question ${i + 1}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={addQ}
          className="mt-3 inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          <Plus className="h-4 w-4" />
          Add question
        </button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 transition hover:border-gray-300"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          disabled={!canSave}
          className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
        >
          {initial ? "Save changes" : "Create template"}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-gray-600">
        {label} {required && <span className="text-rose-500">*</span>}
      </span>
      {hint && <span className="mt-0.5 block text-[11px] text-gray-400">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}
