"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, Plus, Send, Trash2, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/lib/auth";
import {
  buildVoucher,
  listRateCards,
  submitVoucher,
  type ParticipantInput,
  type RateCardLite,
} from "@/lib/erpApi";
import { money } from "@/lib/erpFormat";
import type { Voucher } from "@/types/erp";

/**
 * Voucher builder — turn a list of participants into one payment voucher.
 *
 * Each row captures what finance does by hand today: the rate (from a saved
 * rate card or entered directly), how many days, what the org already covered
 * that day (food / lodging / incidentals → the per-diem is reduced), and any
 * reimbursable receipts. "Build" computes every payable deterministically;
 * "Submit" opens the workflow transaction and routes it to compliance.
 */

type Row = {
  participant_name: string;
  role: string;
  rate_card_id: string;
  rate_per_day: string;
  num_days: string;
  meals: boolean;
  lodging: boolean;
  incidentals: boolean;
  transport: string; // reimbursable transport receipts total
  other: string; // reimbursable other (printing, etc.)
};

function emptyRow(): Row {
  return {
    participant_name: "",
    role: "",
    rate_card_id: "",
    rate_per_day: "",
    num_days: "",
    meals: true,
    lodging: false,
    incidentals: false,
    transport: "",
    other: "",
  };
}

export default function NewVoucherPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [eventName, setEventName] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [cards, setCards] = useState<RateCardLite[]>([]);
  const [voucher, setVoucher] = useState<Voucher | null>(null);
  const [busy, setBusy] = useState<"build" | "submit" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRateCards().then(setCards).catch(() => setCards([]));
  }, []);

  function update(i: number, patch: Partial<Row>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
    setVoucher(null);
  }
  function addRow() {
    setRows((r) => [...r, emptyRow()]);
    setVoucher(null);
  }
  function removeRow(i: number) {
    setRows((r) => (r.length === 1 ? r : r.filter((_, idx) => idx !== i)));
    setVoucher(null);
  }

  function toParticipants(): ParticipantInput[] {
    return rows
      .filter((r) => r.participant_name.trim())
      .map((r) => {
        const covered: string[] = [];
        if (r.meals) covered.push("meals");
        if (r.lodging) covered.push("lodging");
        if (r.incidentals) covered.push("incidentals");
        const receipts: ParticipantInput["receipts"] = [];
        const t = parseFloat(r.transport);
        const o = parseFloat(r.other);
        if (!Number.isNaN(t) && t > 0) receipts.push({ filename: "transport", amount: t, category: "transport" });
        if (!Number.isNaN(o) && o > 0) receipts.push({ filename: "other", amount: o, category: "other" });
        const p: ParticipantInput = {
          participant_name: r.participant_name.trim(),
          num_days: parseInt(r.num_days || "0", 10),
          default_covered: covered,
          receipts,
        };
        if (r.role.trim()) p.role = r.role.trim();
        if (r.rate_card_id) p.rate_card_id = r.rate_card_id;
        else if (r.rate_per_day) p.rate_per_day = parseFloat(r.rate_per_day);
        return p;
      });
  }

  async function build() {
    setError(null);
    const participants = toParticipants();
    if (!eventName.trim()) return setError("Give the event a name.");
    if (participants.length === 0) return setError("Add at least one participant with a name.");
    setBusy("build");
    try {
      const v = await buildVoucher({ event_name: eventName.trim(), created_by: user?.name, participants });
      setVoucher(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build the voucher.");
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    if (!voucher) return;
    setBusy("submit");
    setError(null);
    try {
      const v = await submitVoucher(voucher.id);
      router.push(`/transactions/${encodeURIComponent(v.txn_ref ?? "")}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit the voucher.");
      setBusy(null);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-6 py-8">
        <header className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">Finance</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-gray-900">New payment voucher</h1>
          <p className="mt-1 text-sm text-gray-500">
            Add each participant, and DOCex computes the per-diem (less anything the org covered) plus
            reimbursements. Submit to route it through compliance and finance.
          </p>
        </header>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p>
        )}

        <div className="mb-4 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <label className="mb-1 block text-xs font-medium text-gray-700">Event</label>
          <input
            value={eventName}
            onChange={(e) => {
              setEventName(e.target.value);
              setVoucher(null);
            }}
            placeholder="e.g. Q3 Partner Workshop — Abuja"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
        </div>

        {/* Participant rows */}
        <div className="space-y-3">
          {rows.map((row, i) => (
            <div key={i} className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  <Users className="h-3.5 w-3.5" /> Participant {i + 1}
                </span>
                {rows.length > 1 && (
                  <button type="button" onClick={() => removeRow(i)} className="text-gray-300 transition hover:text-red-500">
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Name">
                  <input
                    value={row.participant_name}
                    onChange={(e) => update(i, { participant_name: e.target.value })}
                    placeholder="Full name"
                    className={inputCls}
                  />
                </Field>
                <Field label="Role (optional)">
                  <input
                    value={row.role}
                    onChange={(e) => update(i, { role: e.target.value })}
                    placeholder="Facilitator / Participant"
                    className={inputCls}
                  />
                </Field>

                <Field label="Rate card">
                  <select
                    value={row.rate_card_id}
                    onChange={(e) => update(i, { rate_card_id: e.target.value })}
                    className={inputCls}
                  >
                    <option value="">— enter rate manually —</option>
                    {cards.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({money(c.default_rate_per_day, c.currency)}/day)
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Rate / day">
                  <input
                    value={row.rate_per_day}
                    onChange={(e) => update(i, { rate_per_day: e.target.value })}
                    placeholder="e.g. 20000"
                    inputMode="numeric"
                    disabled={!!row.rate_card_id}
                    className={inputCls + (row.rate_card_id ? " bg-gray-50 text-gray-400" : "")}
                  />
                </Field>

                <Field label="Days attended">
                  <input
                    value={row.num_days}
                    onChange={(e) => update(i, { num_days: e.target.value })}
                    placeholder="e.g. 3"
                    inputMode="numeric"
                    className={inputCls}
                  />
                </Field>
                <Field label="Org covered each day">
                  <div className="flex flex-wrap items-center gap-3 pt-1.5">
                    <Check label="Food" checked={row.meals} onChange={(v) => update(i, { meals: v })} />
                    <Check label="Lodging" checked={row.lodging} onChange={(v) => update(i, { lodging: v })} />
                    <Check label="Incidentals" checked={row.incidentals} onChange={(v) => update(i, { incidentals: v })} />
                  </div>
                </Field>

                <Field label="Transport receipts (₦)">
                  <input
                    value={row.transport}
                    onChange={(e) => update(i, { transport: e.target.value })}
                    placeholder="reimbursable total"
                    inputMode="numeric"
                    className={inputCls}
                  />
                </Field>
                <Field label="Other receipts (₦)">
                  <input
                    value={row.other}
                    onChange={(e) => update(i, { other: e.target.value })}
                    placeholder="printing, etc."
                    inputMode="numeric"
                    className={inputCls}
                  />
                </Field>
              </div>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={addRow}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
        >
          <Plus className="h-4 w-4" /> Add participant
        </button>

        {/* Preview */}
        {voucher && (
          <div className="mt-6 rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-100 px-5 py-3">
              <h2 className="text-sm font-semibold text-gray-900">Voucher preview — {voucher.event_name}</h2>
              <p className="text-xs text-gray-400">
                {voucher.participant_count} participant{voucher.participant_count === 1 ? "" : "s"}
                {voucher.flagged_count > 0 && (
                  <span className="ml-1 font-medium text-amber-600">· {voucher.flagged_count} need review</span>
                )}
              </p>
            </div>
            <ul className="divide-y divide-gray-50">
              {voucher.lines.map((l, i) => (
                <li key={i} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium text-gray-900">{l.participant_name}</span>
                    {l.role && <span className="text-gray-400"> · {l.role}</span>}
                    <span className="block text-xs text-gray-400">
                      {l.days}d per-diem {money(l.per_diem_entitlement, voucher.currency)} + reimb{" "}
                      {money(l.reimbursable_total, voucher.currency)}
                      {l.flag_count > 0 && <span className="text-amber-600"> · flagged</span>}
                    </span>
                  </span>
                  <span className="font-semibold text-gray-900">{money(l.amount, voucher.currency)}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3">
              <span className="text-sm font-semibold text-gray-900">Total</span>
              <span className="text-lg font-bold text-brand-700">{money(voucher.total, voucher.currency)}</span>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="mt-6 flex items-center gap-3">
          <button
            type="button"
            onClick={build}
            disabled={busy !== null}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-60"
          >
            {busy === "build" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
            {voucher ? "Rebuild" : "Build voucher"}
          </button>
          {voucher && (
            <button
              type="button"
              onClick={submit}
              disabled={busy !== null}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-60"
            >
              {busy === "submit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Submit for review
            </button>
          )}
        </div>
      </div>
    </AppShell>
  );
}

const inputCls =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-gray-600">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-gray-300 text-brand-600 focus:ring-brand-200"
      />
      {label}
    </label>
  );
}
