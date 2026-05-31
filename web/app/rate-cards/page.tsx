"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  CircleDollarSign,
  Loader2,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  createRateCard,
  deleteRateCard,
  listRateCards,
  updateRateCard,
} from "@/lib/api";
import { GuidanceCard } from "@/components/GuidanceCard";
import type { RateCard, RateLine } from "@/types";

/**
 * /rate-cards — manage reusable per-diem schedules.
 *
 * One card holds:
 *   - A name (e.g. "TA Connect Standard 2026")
 *   - A default per-diem rate (applied when role lookup misses)
 *   - Zero or more per-role rates (Facilitator vs Participant vs M&E)
 *
 * Cards are consumed by the Attendance Payment Agent — when you run an
 * event you pick the card, and the agent applies the right rate to each
 * person based on their role column in the payment info form.
 *
 * Editing is in-place: clicking a card swaps its body to a form with
 * add/remove row buttons. No modal — keeps the spatial relationship
 * between the saved card and its draft form intact.
 */

export default function RateCardsPage() {
  const [cards, setCards] = useState<RateCard[] | null>(null);
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setError(null);
    try {
      const list = await listRateCards();
      setCards(list);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load rate cards. Is the API running on port 8000?",
      );
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  return (
    <div className="min-h-screen bg-[#fafaf7]">
      <header className="sticky top-0 z-50 border-b border-gray-100 bg-white shadow-sm">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between gap-6 px-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-400 transition-colors hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="text-lg font-bold text-brand-600">DOCex</span>
          </Link>
          <span className="hidden items-center gap-1.5 text-sm font-medium text-gray-500 sm:inline-flex">
            <CircleDollarSign className="h-4 w-4 text-brand-600" />
            Rate cards
          </span>
          <Link
            href="/agents/attendance-payment"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
          >
            Attendance Agent
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="space-y-8">
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                Rate cards
              </h1>
              <p className="mt-2 max-w-xl text-base text-gray-600">
                Define your per-diem schedule once, reuse it across every
                event.{" "}
                <span className="text-gray-900">
                  Each card has a default rate plus per-role overrides
                </span>{" "}
                — Facilitators, Participants, M&E Officers, whatever your
                org distinguishes.
              </p>
            </div>
            {editingId === null && (
              <button
                type="button"
                onClick={() => setEditingId("new")}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
              >
                <Plus className="h-4 w-4" />
                New rate card
              </button>
            )}
          </div>

          <GuidanceCard title="How rate cards drive payments">
            When you run the Attendance Payment Agent, pick a card. The agent
            looks up each payee's <span className="font-medium">Role</span>{" "}
            column in their payment info form, finds the matching rate, and
            multiplies by days attended. If a role isn't listed on the card,
            the default rate is used. Cards are snapshot onto each run so
            future edits never alter past audit trails.
          </GuidanceCard>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {cards === null && !error && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading rate cards…
            </div>
          )}

          {/* New card form */}
          {editingId === "new" && (
            <CardEditor
              card={null}
              onCancel={() => setEditingId(null)}
              onSave={async (payload) => {
                await createRateCard(payload);
                setEditingId(null);
                await reload();
              }}
            />
          )}

          {/* List */}
          {cards !== null && cards.length === 0 && editingId === null && !error && (
            <EmptyState onCreate={() => setEditingId("new")} />
          )}

          {cards !== null && cards.length > 0 && (
            <div className="grid gap-3">
              {cards.map((c) =>
                editingId === c.id ? (
                  <CardEditor
                    key={c.id}
                    card={c}
                    onCancel={() => setEditingId(null)}
                    onSave={async (payload) => {
                      await updateRateCard(c.id, payload);
                      setEditingId(null);
                      await reload();
                    }}
                  />
                ) : (
                  <CardView
                    key={c.id}
                    card={c}
                    onEdit={() => setEditingId(c.id)}
                    onDelete={async () => {
                      const ok = window.confirm(
                        `Delete rate card "${c.name}"? Past runs that used this card keep their snapshot — only future runs lose it.`,
                      );
                      if (!ok) return;
                      await deleteRateCard(c.id);
                      await reload();
                    }}
                  />
                ),
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

/* ─── Card view (read-only) ─────────────────────────────────────────────── */

function CardView({
  card,
  onEdit,
  onDelete,
}: {
  card: RateCard;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-gray-900">
            {card.name}
          </h3>
          <p className="mt-1 text-xs text-gray-500">
            Default ₦{card.default_rate_per_day.toLocaleString()}/day ·{" "}
            {card.roles.length}{" "}
            {card.roles.length === 1 ? "role override" : "role overrides"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onEdit}
            className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-brand-700"
            title="Edit"
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-md p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-rose-700"
            title="Delete"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {card.roles.length > 0 && (
        <div className="mt-4 grid gap-1.5 sm:grid-cols-2">
          {card.roles.map((r, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50/40 px-3 py-2 text-sm"
            >
              <span className="font-medium text-gray-700">{r.role}</span>
              <span className="tabular-nums text-gray-900">
                ₦{r.amount_per_day.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Card editor (create + update) ─────────────────────────────────────── */

function CardEditor({
  card,
  onCancel,
  onSave,
}: {
  card: RateCard | null;
  onCancel: () => void;
  onSave: (payload: {
    name: string;
    default_rate_per_day: number;
    roles: RateLine[];
  }) => Promise<void>;
}) {
  const [name, setName] = useState(card?.name ?? "");
  const [defaultRate, setDefaultRate] = useState<string>(
    card ? String(card.default_rate_per_day) : "",
  );
  const [roles, setRoles] = useState<RateLine[]>(card?.roles ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addRole() {
    setRoles((r) => [...r, { role: "", amount_per_day: 0 }]);
  }
  function updateRole(i: number, patch: Partial<RateLine>) {
    setRoles((r) => r.map((x, j) => (i === j ? { ...x, ...patch } : x)));
  }
  function removeRole(i: number) {
    setRoles((r) => r.filter((_, j) => i !== j));
  }

  async function save() {
    setError(null);
    const rate = parseFloat(defaultRate);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!Number.isFinite(rate) || rate <= 0) {
      setError("Default rate must be a positive number.");
      return;
    }
    const cleanRoles = roles
      .map((r) => ({ role: r.role.trim(), amount_per_day: Number(r.amount_per_day) }))
      .filter((r) => r.role && Number.isFinite(r.amount_per_day) && r.amount_per_day > 0);
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        default_rate_per_day: rate,
        roles: cleanRoles,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border-2 border-brand-200 bg-brand-50/20 p-5 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-700">
        <Sparkles className="h-4 w-4" />
        {card ? "Editing rate card" : "New rate card"}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label className="text-xs font-medium text-gray-600">Card name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. TA Connect Standard 2026"
            className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600">
            Default rate per day (NGN)
          </label>
          <input
            type="number"
            min="0"
            step="500"
            value={defaultRate}
            onChange={(e) => setDefaultRate(e.target.value)}
            placeholder="15000"
            className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <p className="mt-1 text-[11px] text-gray-400">
            Applied to attendees whose role isn't in the list below
          </p>
        </div>
      </div>

      <div className="mt-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Per-role rates (optional)
          </p>
          <button
            type="button"
            onClick={addRole}
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:border-brand-300 hover:text-brand-700"
          >
            <Plus className="h-3 w-3" />
            Add role
          </button>
        </div>

        {roles.length === 0 ? (
          <p className="mt-2 text-[11px] italic text-gray-400">
            No role overrides yet — every attendee gets the default rate.
            Add one to differentiate (e.g. Facilitators ₦30k, Participants
            ₦15k).
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {roles.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="text"
                  value={r.role}
                  onChange={(e) => updateRole(i, { role: e.target.value })}
                  placeholder="Role (e.g. Facilitator)"
                  className="flex-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none"
                />
                <span className="text-sm text-gray-400">₦</span>
                <input
                  type="number"
                  min="0"
                  step="500"
                  value={r.amount_per_day || ""}
                  onChange={(e) =>
                    updateRole(i, {
                      amount_per_day: parseFloat(e.target.value) || 0,
                    })
                  }
                  placeholder="30000"
                  className="w-28 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-sm placeholder:text-gray-400 focus:border-brand-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => removeRole(i)}
                  className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-rose-700"
                  title="Remove"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="mt-5 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:border-gray-300 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              <Save className="h-3.5 w-3.5" />
              Save
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white px-6 py-16 text-center">
      <div className="mx-auto mb-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <CircleDollarSign className="h-7 w-7" />
      </div>
      <h2 className="text-xl font-semibold text-gray-900">
        Create your first rate card
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-600">
        Define your standard per-diem rates once. Every event run pulls
        from the card — no more typing ₦15,000 into the wizard from memory.
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm shadow-brand-100 transition hover:bg-brand-700"
      >
        <Sparkles className="h-4 w-4" />
        New rate card
      </button>
    </div>
  );
}
