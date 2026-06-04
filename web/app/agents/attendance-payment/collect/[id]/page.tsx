"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  Copy,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  Users,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  buildCollectionRun,
  getCollection,
  updateCollection,
} from "@/lib/api";
import type { AttendanceCollection, CollectedAttendee } from "@/types";

function blankAttendee(): CollectedAttendee {
  return {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `a_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    name: "",
    organisation: "",
    account_number: "",
    bank_code: "",
    bank_name: "",
    role: "",
    present_days: [],
    source: "organizer",
  };
}

export default function CollectionGridPage({
  params,
}: {
  params: { id: string };
}) {
  const router = useRouter();
  const { id } = params;

  const [collection, setCollection] = useState<AttendanceCollection | null>(null);
  const [attendees, setAttendees] = useState<CollectedAttendee[]>([]);
  const [rate, setRate] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [shareUrl, setShareUrl] = useState("");

  const load = useCallback(async () => {
    try {
      const c = await getCollection(id);
      setCollection(c);
      setAttendees(c.attendees.length ? c.attendees : []);
      setRate(c.rate_per_day ? String(c.rate_per_day) : "");
      if (typeof window !== "undefined") {
        setShareUrl(`${window.location.origin}/checkin/${c.share_token}`);
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load this collection.");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  function patchAttendee(aid: string, patch: Partial<CollectedAttendee>) {
    setAttendees((list) => list.map((a) => (a.id === aid ? { ...a, ...patch } : a)));
  }
  function togglePresent(aid: string, day: string) {
    setAttendees((list) =>
      list.map((a) => {
        if (a.id !== aid) return a;
        const has = a.present_days.includes(day);
        return {
          ...a,
          present_days: has
            ? a.present_days.filter((d) => d !== day)
            : [...a.present_days, day],
        };
      }),
    );
  }

  async function save(): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateCollection(id, {
        attendees,
        rate_per_day: Number(rate) || 0,
      });
      setCollection(updated);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function build() {
    setBuilding(true);
    setError(null);
    const ok = await save();
    if (!ok) {
      setBuilding(false);
      return;
    }
    try {
      const { run_id } = await buildCollectionRun(id);
      router.push(`/agents/attendance-payment/${run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the run.");
      setBuilding(false);
    }
  }

  async function copyLink() {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const days = collection?.day_labels ?? [];
  const withBank = attendees.filter((a) => a.account_number.trim()).length;

  return (
    <AppShell
      active="attendance"
      actions={
        <>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700"
            title="Pull in any new self-check-ins"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Save
          </button>
        </>
      }
    >
      <main className="mx-auto max-w-5xl px-6 py-10">
        {loadError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            {loadError}
          </div>
        ) : !collection ? (
          <div className="flex items-center gap-2 py-24 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                {collection.event_name}
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                {attendees.length} attendee{attendees.length === 1 ? "" : "s"} ·{" "}
                {days.length} day{days.length === 1 ? "" : "s"} · {withBank} with bank details
              </p>
            </div>

            {/* Share link */}
            <div className="rounded-xl border border-gray-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Self check-in link
              </p>
              <p className="mt-1 text-xs text-gray-500">
                Share this with attendees so they enter their own name and bank
                details. Hit Refresh to pull them in.
              </p>
              <div className="mt-3 flex items-center gap-2">
                <input
                  readOnly
                  value={shareUrl}
                  className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700"
                />
                <button
                  type="button"
                  onClick={copyLink}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-brand-700"
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? "Copied" : "Copy link"}
                </button>
              </div>
            </div>

            {/* Rate */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700">
                Per-day rate (₦)
              </label>
              <input
                type="number"
                min={0}
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder="15000"
                className="w-36 rounded-lg border border-gray-200 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>

            {/* Grid */}
            <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50/60 text-left text-xs uppercase tracking-wide text-gray-500">
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Org</th>
                    <th className="px-3 py-2 font-medium">Bank code</th>
                    <th className="px-3 py-2 font-medium">Account no.</th>
                    {days.map((d) => (
                      <th key={d} className="px-2 py-2 text-center font-medium">
                        {d.replace("Day ", "D")}
                      </th>
                    ))}
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {attendees.length === 0 ? (
                    <tr>
                      <td colSpan={5 + days.length} className="px-3 py-10 text-center text-sm text-gray-500">
                        No attendees yet. Add a row below, or share the
                        check-in link.
                      </td>
                    </tr>
                  ) : (
                    attendees.map((a) => (
                      <tr key={a.id} className="border-b border-gray-50 last:border-0">
                        <td className="px-2 py-1.5">
                          <input
                            value={a.name}
                            onChange={(e) => patchAttendee(a.id, { name: e.target.value })}
                            placeholder="Full name"
                            className="w-36 rounded-md border border-transparent bg-transparent px-2 py-1 focus:border-gray-200 focus:bg-white focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            value={a.organisation ?? ""}
                            onChange={(e) => patchAttendee(a.id, { organisation: e.target.value })}
                            placeholder="Org"
                            className="w-28 rounded-md border border-transparent bg-transparent px-2 py-1 focus:border-gray-200 focus:bg-white focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            value={a.bank_code}
                            onChange={(e) => patchAttendee(a.id, { bank_code: e.target.value })}
                            placeholder="058"
                            className="w-16 rounded-md border border-transparent bg-transparent px-2 py-1 focus:border-gray-200 focus:bg-white focus:outline-none"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            value={a.account_number}
                            onChange={(e) => patchAttendee(a.id, { account_number: e.target.value })}
                            placeholder="10 digits"
                            className="w-28 rounded-md border border-transparent bg-transparent px-2 py-1 focus:border-gray-200 focus:bg-white focus:outline-none"
                          />
                        </td>
                        {days.map((d) => (
                          <td key={d} className="px-2 py-1.5 text-center">
                            <input
                              type="checkbox"
                              checked={a.present_days.includes(d)}
                              onChange={() => togglePresent(a.id, d)}
                              className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                            />
                          </td>
                        ))}
                        <td className="px-2 py-1.5 text-right">
                          <button
                            type="button"
                            onClick={() => setAttendees((l) => l.filter((x) => x.id !== a.id))}
                            className="rounded-md p-1 text-gray-400 transition hover:bg-rose-50 hover:text-rose-600"
                            aria-label="Remove attendee"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <button
              type="button"
              onClick={() => setAttendees((l) => [...l, blankAttendee()])}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:border-brand-300 hover:text-brand-700"
            >
              <Plus className="h-4 w-4" />
              Add attendee
            </button>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <div className="flex items-center justify-between border-t border-gray-200 pt-6">
              <Link
                href="/agents/attendance-payment"
                className="text-sm font-medium text-gray-500 transition hover:text-gray-800"
              >
                ← All runs
              </Link>
              <button
                type="button"
                onClick={build}
                disabled={building || attendees.length === 0}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
              >
                {building ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Building…
                  </>
                ) : (
                  <>
                    <Users className="h-4 w-4" />
                    Build payment schedule
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </main>
    </AppShell>
  );
}
