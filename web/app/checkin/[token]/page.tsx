"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { getPublicCollection, selfCheckIn } from "@/lib/api";
import type { PublicCollectionInfo } from "@/types";

/**
 * Public self-check-in page. No nav, no auth — an attendee opens the shared
 * link, enters their name + bank details, ticks the days they attended, and
 * submits. The data flows straight into the organiser's collection grid.
 */
export default function CheckInPage({
  params,
}: {
  params: { token: string };
}) {
  const { token } = params;

  const [info, setInfo] = useState<PublicCollectionInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [bankName, setBankName] = useState("");
  const [bankCode, setBankCode] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [presentDays, setPresentDays] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInfo(await getPublicCollection(token));
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "This check-in link isn't valid.",
      );
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleDay(d: string) {
    setPresentDays((days) =>
      days.includes(d) ? days.filter((x) => x !== d) : [...days, d],
    );
  }

  async function submit() {
    if (!name.trim()) {
      setError("Please enter your name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await selfCheckIn(token, {
        name: name.trim(),
        organisation: org.trim() || undefined,
        account_number: accountNumber.trim() || undefined,
        bank_code: bankCode.trim() || undefined,
        bank_name: bankName.trim() || undefined,
        present_days: presentDays,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#fafaf7]">
      <header className="border-b border-gray-100 bg-white">
        <div className="mx-auto flex h-16 max-w-xl items-center px-6">
          <span className="text-lg font-bold tracking-tight text-brand-600">DOCex</span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-xl flex-1 px-6 py-10">
        {loadError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            {loadError}
          </div>
        ) : !info ? (
          <div className="flex items-center gap-2 py-24 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : done ? (
          <div className="rounded-2xl border border-emerald-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <h1 className="mt-4 text-xl font-semibold text-gray-900">You're checked in</h1>
            <p className="mt-2 text-sm text-gray-600">
              Thanks, {name.trim()}. Your details have been sent to the
              organiser for {info.event_name}.
            </p>
            <button
              type="button"
              onClick={() => {
                setDone(false);
                setName("");
                setOrg("");
                setBankName("");
                setBankCode("");
                setAccountNumber("");
                setPresentDays([]);
              }}
              className="mt-6 text-sm font-medium text-brand-700 underline-offset-4 hover:underline"
            >
              Check in someone else
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600">
                <Sparkles className="h-3 w-3 text-brand-600" />
                Check-in
              </div>
              <h1 className="mt-4 text-2xl font-bold tracking-tight text-gray-900">
                {info.event_name}
              </h1>
              <p className="mt-1 text-sm text-gray-600">
                Enter your details so you can be paid. Your bank account is only
                used to verify your name against the bank record.
              </p>
            </div>

            <div className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <Field label="Full name (as on your bank account)" required>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </Field>
              <Field label="Organisation">
                <input
                  value={org}
                  onChange={(e) => setOrg(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Bank name">
                  <input
                    value={bankName}
                    onChange={(e) => setBankName(e.target.value)}
                    placeholder="e.g. GTBank"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                </Field>
                <Field label="Bank code">
                  <input
                    value={bankCode}
                    onChange={(e) => setBankCode(e.target.value)}
                    placeholder="058"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                </Field>
              </div>
              <Field label="Account number">
                <input
                  value={accountNumber}
                  onChange={(e) => setAccountNumber(e.target.value)}
                  inputMode="numeric"
                  placeholder="10-digit NUBAN"
                  className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </Field>

              {info.day_labels.length > 0 && (
                <Field label="Which days did you attend?">
                  <div className="flex flex-wrap gap-2">
                    {info.day_labels.map((d) => {
                      const on = presentDays.includes(d);
                      return (
                        <button
                          key={d}
                          type="button"
                          onClick={() => toggleDay(d)}
                          className={
                            "rounded-lg border px-3 py-1.5 text-sm font-medium transition " +
                            (on
                              ? "border-brand-300 bg-brand-50 text-brand-700"
                              : "border-gray-200 bg-white text-gray-600 hover:border-brand-300")
                          }
                        >
                          {d}
                        </button>
                      );
                    })}
                  </div>
                </Field>
              )}
            </div>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Submitting…
                </>
              ) : (
                "Check in"
              )}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">
        {label} {required && <span className="text-rose-500">*</span>}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}
