"use client";

import {
  STARTER_TEMPLATES,
  type QuestionTemplate,
  type TemplateQuestion,
  type TemplateCategory,
} from "@/lib/templates";

/**
 * Template store.
 *
 * Merges the built-in STARTER_TEMPLATES (locked, clonable) with the user's
 * own saved templates. Persistence is browser-local (localStorage) for now —
 * created templates survive refreshes on this machine and demo cleanly,
 * and the same shape swaps to Supabase in Phase 2 with no UI changes.
 *
 * SSR-safe: every read guards `typeof window`, so importing this on the
 * server (Next.js prerender) returns just the starters.
 */

const STORAGE_KEY = "docex.templates.v1";

export type StoredTemplate = QuestionTemplate & {
  starter?: false;
  createdAt: string;
  updatedAt: string;
};

export const TEMPLATE_CATEGORIES: {
  id: TemplateCategory;
  label: string;
  blurb: string;
}[] = [
  { id: "screen", label: "Screen & review", blurb: "Shortlist or assess document bundles against standard questions." },
  { id: "reconcile", label: "Reconcile", blurb: "Cross-check two documents that should agree (e.g. financial vs service)." },
  { id: "extract", label: "Extract", blurb: "Pull structured fields out of each document into one row." },
  { id: "compare", label: "Compare", blurb: "Compare many documents side by side on the same questions." },
];

function safeRead(): StoredTemplate[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as StoredTemplate[]) : [];
  } catch {
    // Corrupt payload — fail soft to "no user templates" rather than crash.
    return [];
  }
}

function safeWrite(templates: StoredTemplate[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(templates));
}

function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `tpl_${crypto.randomUUID()}`;
  }
  return `tpl_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

/** Starters only — always available, even on the server. */
export function listStarterTemplates(): QuestionTemplate[] {
  return STARTER_TEMPLATES;
}

/** The user's saved templates (newest first). Empty on the server. */
export function listUserTemplates(): StoredTemplate[] {
  return safeRead().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

/** Everything the chooser should show: starters + user templates. */
export function listAllTemplates(): QuestionTemplate[] {
  return [...STARTER_TEMPLATES, ...listUserTemplates()];
}

export function getTemplate(id: string): QuestionTemplate | undefined {
  return listAllTemplates().find((t) => t.id === id);
}

export interface TemplateInput {
  name: string;
  description: string;
  category?: TemplateCategory;
  defaultContext?: string;
  questions: TemplateQuestion[];
}

/** Create a new user template; returns the saved record. */
export function createTemplate(input: TemplateInput): StoredTemplate {
  const now = new Date().toISOString();
  const record: StoredTemplate = {
    id: uid(),
    starter: false,
    createdAt: now,
    updatedAt: now,
    name: input.name.trim(),
    description: input.description.trim(),
    category: input.category,
    defaultContext: input.defaultContext?.trim() || undefined,
    questions: cleanQuestions(input.questions),
  };
  safeWrite([record, ...safeRead()]);
  return record;
}

/** Update an existing user template. No-op for starters. */
export function updateTemplate(
  id: string,
  input: TemplateInput,
): StoredTemplate | undefined {
  const all = safeRead();
  const idx = all.findIndex((t) => t.id === id);
  if (idx === -1) return undefined;
  const updated: StoredTemplate = {
    ...all[idx],
    name: input.name.trim(),
    description: input.description.trim(),
    category: input.category,
    defaultContext: input.defaultContext?.trim() || undefined,
    questions: cleanQuestions(input.questions),
    updatedAt: new Date().toISOString(),
  };
  all[idx] = updated;
  safeWrite(all);
  return updated;
}

export function deleteTemplate(id: string): void {
  safeWrite(safeRead().filter((t) => t.id !== id));
}

/**
 * Duplicate any template (starter or user) into a new editable user copy.
 * Returns the new record so the caller can jump straight into editing it.
 */
export function duplicateTemplate(id: string): StoredTemplate | undefined {
  const source = getTemplate(id);
  if (!source) return undefined;
  return createTemplate({
    name: `${source.name} (copy)`,
    description: source.description,
    category: source.category,
    defaultContext: source.defaultContext,
    questions: source.questions.map((q) => ({ text: q.text, hint: q.hint })),
  });
}

export function isStarter(id: string): boolean {
  return STARTER_TEMPLATES.some((t) => t.id === id);
}

function cleanQuestions(qs: TemplateQuestion[]): TemplateQuestion[] {
  return qs
    .map((q) => ({
      text: q.text.trim(),
      hint: q.hint?.trim() || undefined,
    }))
    .filter((q) => q.text.length > 0);
}
