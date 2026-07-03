"use client";

import type { FormFieldSpec } from "@/types";

/**
 * Renders whatever fields a PaymentType's form_fields describe.
 *
 * Deliberately generic: it has no knowledge of "Travel Advance" or any
 * other specific payment type. Any org can define its own form-mode
 * payment type (different names, different fields, different labels) in
 * the org profile, and this component renders it correctly — the fields
 * come entirely from data, not from a hardcoded per-type component.
 */

const inputClass =
  "w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100";

interface DynamicFormFieldsProps {
  fields: FormFieldSpec[];
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
  // Live option lists keyed by choices_source (today just one: the org's
  // approved vendor list). A field with choices_source set reads its
  // options from here instead of its own (possibly empty/stale) `choices`
  // array — this is what keeps a Vendor Payment form current the moment
  // the org edits its vendor list, with no form re-configuration needed.
  liveChoices?: Partial<Record<string, string[]>>;
}

export function DynamicFormFields({
  fields,
  values,
  onChange,
  liveChoices = {},
}: DynamicFormFieldsProps) {
  if (fields.length === 0) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map((field) => {
        const value = values[field.name] ?? "";
        const label = (
          <label
            key={`label-${field.name}`}
            className="block text-sm font-semibold text-gray-900"
          >
            {field.label}
            {!field.required && (
              <span className="font-normal text-gray-400"> (optional)</span>
            )}
          </label>
        );

        if (field.type === "choice") {
          const options = field.choices_source
            ? (liveChoices[field.choices_source] ?? [])
            : field.choices;
          return (
            <div key={field.name} className="space-y-1.5">
              {label}
              <select
                value={value}
                required={field.required}
                onChange={(e) => onChange(field.name, e.target.value)}
                className={inputClass}
              >
                <option value="">Select…</option>
                {options.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              {field.choices_source && options.length === 0 && (
                <p className="text-xs text-amber-700">
                  No options configured yet — ask your admin to add entries
                  to the org profile.
                </p>
              )}
            </div>
          );
        }

        // currency/number/email/date/text all map onto a plain <input>;
        // only the `type` and a couple of presentation details change.
        const inputType =
          field.type === "currency"
            ? "number"
            : field.type === "number"
              ? "number"
              : field.type; // "text" | "date" | "email"

        return (
          <div key={field.name} className="space-y-1.5">
            {label}
            <div className="relative">
              {field.type === "currency" && (
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">
                  ₦
                </span>
              )}
              <input
                type={inputType}
                value={value}
                required={field.required}
                onChange={(e) => onChange(field.name, e.target.value)}
                className={field.type === "currency" ? `${inputClass} pl-7` : inputClass}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
