"use client";

import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { summarizeForAssistant } from "@/lib/api";
import type { AssistantBrief as Brief } from "@/types";
import { urgencyColor, urgencyDot } from "@/types";

/**
 * <AssistantBrief>
 *
 * The agentic narrator that sits at the top of every result page. Calls
 * /assistant/summarize with the result payload, renders Claude's plain-
 * English briefing + ranked next-action buttons.
 *
 * Why this exists: the verdict table is the WHAT — accurate but cold.
 * The Assistant gives the WHY/SO-WHAT — synthesised, actionable, human.
 * That's the single biggest agentic-feel upgrade in DOCex.
 *
 * Behaviour:
 *   - Skeleton loader while Claude is thinking (~2-4s).
 *   - Subtle fade-in transition when the brief lands.
 *   - On API failure, surfaces a soft inline error — the result table
 *     below still works without the brief.
 *   - Optional onAction prop lets the parent page wire suggested actions
 *     to real handlers (e.g. "Block this payment" → trigger the existing
 *     block flow). When omitted, action labels render as inert chips.
 */

export function AssistantBrief({
  contextKind,
  contextId,
  payload,
  onAction,
}: {
  contextKind: string;
  contextId?: string;
  payload: unknown;
  onAction?: (actionLabel: string) => void;
}) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setBrief(null);
    (async () => {
      try {
        const b = await summarizeForAssistant(contextKind, payload, contextId);
        if (!cancelled) setBrief(b);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Couldn't reach the Assistant — your data is below.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // We intentionally don't re-run when payload object identity changes —
    // only when the contextId does. The brief is keyed to the result the
    // user is looking at, not to every reference re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextKind, contextId]);

  if (loading) {
    return <Skeleton />;
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          <Sparkles className="h-3.5 w-3.5" />
          DOCex Assistant
        </div>
        <p className="mt-2 text-sm text-gray-500">{error}</p>
      </div>
    );
  }

  if (!brief) return null;

  return (
    <div
      className="overflow-hidden rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/40 via-white to-white p-5 shadow-sm animate-in fade-in slide-in-from-top-1 duration-300"
      // Tailwind animate-in classes: we use the data-state pattern from
      // shadcn/Radix. If the project doesn't have tailwindcss-animate
      // installed, these are no-ops — the brief just appears without
      // animation, which still works.
    >
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">
              DOCex Assistant
            </p>
            <span className="text-[11px] text-gray-400">·</span>
            <span className="text-[11px] italic text-gray-400">
              briefed by Claude
            </span>
          </div>

          {brief.headline && (
            <p className="mt-2 text-base font-semibold leading-snug text-gray-900">
              {brief.headline}
            </p>
          )}

          <p
            className={`text-sm leading-relaxed text-gray-700 ${
              brief.headline ? "mt-1" : "mt-2"
            }`}
          >
            {brief.narrative}
          </p>

          {brief.actions.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                Suggested next steps
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {brief.actions.map((a, i) => {
                  const Tag = onAction ? "button" : "span";
                  return (
                    <Tag
                      key={i}
                      type={onAction ? "button" : undefined}
                      onClick={onAction ? () => onAction(a.label) : undefined}
                      title={a.reason ?? undefined}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition ${urgencyColor[a.urgency]} ${
                        onAction ? "cursor-pointer" : "cursor-default"
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${urgencyDot[a.urgency]}`}
                      />
                      {a.label}
                    </Tag>
                  );
                })}
              </div>
              {brief.actions.some((a) => a.reason) && (
                <ul className="mt-2 space-y-0.5 text-[11px] text-gray-500">
                  {brief.actions
                    .filter((a) => a.reason)
                    .map((a, i) => (
                      <li key={i}>
                        <span className="font-medium text-gray-600">
                          {a.label}:
                        </span>{" "}
                        {a.reason}
                      </li>
                    ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Loading skeleton ────────────────────────────────────────────────── */

function Skeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/40 via-white to-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 ring-1 ring-brand-200">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">
              DOCex Assistant
            </p>
            <span className="text-[11px] italic text-gray-400">
              briefing you on this run…
            </span>
          </div>
          <div className="mt-2 space-y-2">
            <div className="h-4 w-3/4 animate-pulse rounded bg-gray-100" />
            <div className="h-3 w-full animate-pulse rounded bg-gray-100" />
            <div className="h-3 w-5/6 animate-pulse rounded bg-gray-100" />
            <div className="h-3 w-2/3 animate-pulse rounded bg-gray-100" />
          </div>
          <div className="mt-4 flex gap-2">
            <div className="h-6 w-20 animate-pulse rounded-full bg-gray-100" />
            <div className="h-6 w-24 animate-pulse rounded-full bg-gray-100" />
            <div className="h-6 w-16 animate-pulse rounded-full bg-gray-100" />
          </div>
        </div>
      </div>
    </div>
  );
}
