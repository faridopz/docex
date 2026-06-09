"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Database, Loader2, RefreshCw } from "lucide-react";
import {
  listIntegrations,
  syncIntegration,
  type IntegrationInfo,
  type IntegrationSyncResult,
} from "@/lib/api";

/**
 * Provider-agnostic integrations panel for the Knowledge Hub. Lists every
 * connector registered on the backend (ERPNext today; other ERPs / drives
 * next) and lets the user sync each one. Adding a backend connector makes it
 * appear here automatically — no UI change needed.
 */
export function IntegrationsPanel({ onSynced }: { onSynced?: () => void }) {
  const [providers, setProviders] = useState<IntegrationInfo[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, IntegrationSyncResult>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function load() {
    try {
      setProviders(await listIntegrations());
    } catch {
      setProviders([]);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function runSync(id: string) {
    setBusy(id);
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      const r = await syncIntegration(id);
      setResults((s) => ({ ...s, [id]: r }));
      await load();
      if (r.ingested > 0) onSynced?.();
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [id]: err instanceof Error ? err.message : "Sync failed.",
      }));
    } finally {
      setBusy(null);
    }
  }

  // Nothing registered, or still loading → render nothing.
  if (!providers || providers.length === 0) return null;

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <Database className="h-4 w-4 text-brand-600" />
        <p className="text-sm font-semibold text-gray-900">
          Connected systems
        </p>
      </div>
      <p className="mt-0.5 text-xs text-gray-500">
        Pull documents from your ERPs and drives so they become searchable here.
      </p>

      <div className="mt-4 space-y-3">
        {providers.map((p) => {
          const r = results[p.id];
          const err = errors[p.id];
          return (
            <div
              key={p.id}
              className="rounded-xl border border-gray-200 bg-gray-50/40 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">{p.label}</p>
                  {p.configured ? (
                    <p className="mt-0.5 text-xs text-gray-500">
                      {p.detail ? (
                        <>
                          Connected to{" "}
                          <span className="font-medium text-gray-700">{p.detail}</span>{" "}
                          ·{" "}
                        </>
                      ) : null}
                      {p.synced} document{p.synced === 1 ? "" : "s"} synced
                    </p>
                  ) : (
                    <p className="mt-0.5 text-xs text-gray-500">
                      Not connected — add this provider&apos;s credentials to the
                      backend .env.
                    </p>
                  )}
                </div>
                {p.configured && (
                  <button
                    type="button"
                    onClick={() => runSync(p.id)}
                    disabled={busy === p.id}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
                  >
                    {busy === p.id ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Syncing…
                      </>
                    ) : (
                      <>
                        <RefreshCw className="h-3.5 w-3.5" />
                        Sync now
                      </>
                    )}
                  </button>
                )}
              </div>

              {r && (
                <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-xs text-emerald-800">
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                  <span>
                    {r.ingested} added · {r.skipped} already synced
                    {r.failed > 0 ? ` · ${r.failed} failed` : ""} (of {r.found} found)
                  </span>
                </div>
              )}
              {err && (
                <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs text-rose-700">
                  {err}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
