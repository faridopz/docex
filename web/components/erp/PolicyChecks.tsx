"use client";

import { AlertTriangle, CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  CHECK_LABEL,
  CHECK_STYLE,
  OVERRIDDEN_STYLE,
  REQ_STATUS_LABEL,
  REQ_STATUS_STYLE,
} from "@/lib/requisitionFormat";
import type { PolicyCheck, ReqStatus } from "@/types/requisition";

/** Colour-coded workflow status pill. */
export function ReqStatusBadge({ status, className }: { status: ReqStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        REQ_STATUS_STYLE[status],
        className,
      )}
    >
      {REQ_STATUS_LABEL[status]}
    </span>
  );
}

/**
 * One deterministic policy check.
 *
 * The three states are distinct on purpose. A FAIL blocks payment. A FAIL that
 * has been released is not "fixed" — it is an exception that now carries a
 * name and a reason, and the auditor will read it, so it gets its own colour
 * rather than quietly turning green.
 */
export function PolicyCheckRow({
  check,
  selectable,
  selected,
  onToggle,
}: {
  check: PolicyCheck;
  /** Show a checkbox so an approver can pick which FAILs to release. */
  selectable?: boolean;
  selected?: boolean;
  onToggle?: (code: string) => void;
}) {
  const isBlocking = check.result === "fail" && !check.overridden;
  const Icon = check.overridden
    ? ShieldAlert
    : check.result === "pass"
      ? CheckCircle2
      : check.result === "warning"
        ? AlertTriangle
        : XCircle;

  return (
    <li
      className={cn(
        "flex gap-3 rounded-lg border p-3",
        isBlocking ? "border-red-200 bg-red-50/40" : "border-gray-200 bg-white",
      )}
    >
      {selectable && check.result === "fail" && !check.overridden ? (
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
          checked={!!selected}
          onChange={() => onToggle?.(check.code)}
          aria-label={`Release ${check.name}`}
        />
      ) : (
        <Icon
          className={cn(
            "mt-0.5 h-4 w-4 shrink-0",
            check.overridden
              ? "text-purple-600"
              : check.result === "pass"
                ? "text-emerald-600"
                : check.result === "warning"
                  ? "text-amber-600"
                  : "text-red-600",
          )}
        />
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-gray-900">{check.name || check.code}</span>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
              check.overridden ? OVERRIDDEN_STYLE : CHECK_STYLE[check.result],
            )}
          >
            {check.overridden ? "Released by override" : CHECK_LABEL[check.result]}
          </span>
        </div>

        {check.message ? (
          <p className="mt-1 text-sm text-gray-600">{check.message}</p>
        ) : null}

        {check.policy_value || check.actual_value ? (
          <dl className="mt-1.5 flex flex-wrap gap-x-6 gap-y-0.5 text-xs text-gray-500">
            {check.policy_value ? (
              <div className="flex gap-1.5">
                <dt className="font-medium text-gray-400">Policy</dt>
                <dd>{check.policy_value}</dd>
              </div>
            ) : null}
            {check.actual_value ? (
              <div className="flex gap-1.5">
                <dt className="font-medium text-gray-400">Requested</dt>
                <dd>{check.actual_value}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}

        {/* An override without these three facts cannot exist — the engine
            refuses it — so if we're rendering one, all of it is on the page. */}
        {check.overridden ? (
          <div className="mt-2 rounded-md border border-purple-200 bg-purple-50 p-2.5 text-xs">
            <p className="font-medium text-purple-900">
              Released by {check.override_by || "an approver"}
              {check.override_authority ? ` — ${check.override_authority}` : ""}
            </p>
            {check.override_reason ? (
              <p className="mt-0.5 text-purple-800">“{check.override_reason}”</p>
            ) : (
              <p className="mt-0.5 font-medium text-red-700">
                No written reason recorded — this will fail an audit.
              </p>
            )}
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** The full check list, ordered so anything blocking is read first. */
export function PolicyCheckList({
  checks,
  selectable,
  selectedCodes,
  onToggle,
}: {
  checks: PolicyCheck[];
  selectable?: boolean;
  selectedCodes?: string[];
  onToggle?: (code: string) => void;
}) {
  if (!checks.length) {
    return <p className="text-sm text-gray-500">No policy checks recorded.</p>;
  }

  const rank = (c: PolicyCheck) =>
    c.result === "fail" && !c.overridden ? 0 : c.overridden ? 1 : c.result === "warning" ? 2 : 3;
  const ordered = [...checks].sort((a, b) => rank(a) - rank(b));

  return (
    <ul className="space-y-2">
      {ordered.map((c) => (
        <PolicyCheckRow
          key={c.code}
          check={c}
          selectable={selectable}
          selected={selectedCodes?.includes(c.code)}
          onToggle={onToggle}
        />
      ))}
    </ul>
  );
}
