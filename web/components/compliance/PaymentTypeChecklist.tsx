"use client";

import { useEffect, useState } from "react";
import { CheckSquare, Info } from "lucide-react";
import { getOrgProfile } from "@/lib/api";
import type { PaymentType } from "@/types";

/**
 * Payment-type picker + required-document checklist. Officers pick the type
 * of payment and see exactly which documents must be in the bundle — a
 * pre-flight against the #1 cause of delay (incomplete documentation). The
 * types are org-configured in Settings; this is read-only here.
 *
 * Lean v1: a visible checklist reminder. Auto-validating that each document is
 * actually present in the upload is a follow-up.
 */
export function PaymentTypeChecklist() {
  const [types, setTypes] = useState<PaymentType[] | null>(null);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getOrgProfile();
        if (!cancelled) setTypes(p.payment_types ?? []);
      } catch {
        if (!cancelled) setTypes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!types || types.length === 0) return null;

  const current = types.find((t) => t.name === selected);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <label className="block text-sm font-semibold text-gray-900">
        Payment type
      </label>
      <p className="mt-0.5 text-xs text-gray-500">
        Pick the type to see the documents this payment must include.
      </p>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      >
        <option value="">Select a payment type…</option>
        {types.map((t) => (
          <option key={t.name} value={t.name}>
            {t.name}
          </option>
        ))}
      </select>

      {current && (
        <div className="mt-3 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Required documents
          </p>
          <ul className="space-y-1">
            {current.required_documents.map((d) => (
              <li
                key={d}
                className="flex items-center gap-2 text-sm text-gray-700"
              >
                <CheckSquare className="h-4 w-4 shrink-0 text-brand-500" />
                {d}
              </li>
            ))}
          </ul>
          {current.notes && (
            <p className="flex items-start gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {current.notes}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
