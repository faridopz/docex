"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarCheck, Loader2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { GuidanceCard } from "@/components/GuidanceCard";
import { createCollection } from "@/lib/api";

/**
 * Create an attendance Collection — the native alternative to importing
 * spreadsheets. Set the event, how many days it runs, and a per-day rate;
 * then fill the grid yourself or share the check-in link.
 */
export default function NewCollectionPage() {
  const router = useRouter();
  const [eventName, setEventName] = useState("");
  const [days, setDays] = useState(1);
  const [rate, setRate] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = eventName.trim().length > 0 && days >= 1 && !submitting;

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const dayLabels = Array.from({ length: days }, (_, i) => `Day ${i + 1}`);
      const c = await createCollection({
        event_name: eventName.trim(),
        day_labels: dayLabels,
        rate_per_day: Number(rate) || 0,
      });
      router.push(`/agents/attendance-payment/collect/${c.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the collection.");
      setSubmitting(false);
    }
  }

  return (
    <AppShell active="attendance">
      <main className="mx-auto max-w-2xl px-6 py-12">
        <div className="space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Collect attendance
            </h1>
            <p className="mt-2 text-base text-gray-600">
              No spreadsheet needed. Set up the event, then add people in a
              grid or share a check-in link for attendees to enter their own
              details.
            </p>
          </div>

          <GuidanceCard title="How this works">
            You'll get an editable grid and a shareable check-in link. Mark who
            attended which days, then build a verified payment schedule — the
            same output as the Excel/Sheets import.
          </GuidanceCard>

          <div className="space-y-5 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
            <label className="block">
              <span className="text-sm font-semibold text-gray-900">Event name</span>
              <input
                value={eventName}
                onChange={(e) => setEventName(e.target.value)}
                placeholder="e.g. Q2 Training — Abuja"
                className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </label>

            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-sm font-semibold text-gray-900">How many days?</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  value={days}
                  onChange={(e) => setDays(Math.max(1, Math.min(31, Number(e.target.value) || 1)))}
                  className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-gray-900">
                  Per-day rate (₦)
                </span>
                <input
                  type="number"
                  min={0}
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                  placeholder="e.g. 15000"
                  className="mt-1.5 w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </label>
            </div>
            <p className="text-xs text-gray-500">
              You can change the rate later, or apply a saved rate card when you
              build the schedule.
            </p>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between border-t border-gray-200 pt-6">
            <Link
              href="/agents/attendance-payment"
              className="text-sm font-medium text-gray-500 transition hover:text-gray-800"
            >
              ← Back
            </Link>
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating…
                </>
              ) : (
                <>
                  <CalendarCheck className="h-4 w-4" />
                  Create & open grid
                </>
              )}
            </button>
          </div>
        </div>
      </main>
    </AppShell>
  );
}
