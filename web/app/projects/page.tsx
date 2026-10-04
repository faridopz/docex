"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Loader2, Plus } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { BudgetBar, ProjectForm } from "@/components/erp/ProjectForm";
import { money, shortDate } from "@/lib/requisitionFormat";
import { createProject, listProjects, type ProjectFigures, type ProjectInput } from "@/lib/projectsApi";

/**
 * Projects & grants — one card per grant: what it has, what has gone out,
 * what is promised, what is left. Green is paid (payments and salaries),
 * amber is committed (requests on their way), grey is free.
 */
export default function ProjectsPage() {
  const [rows, setRows] = useState<ProjectFigures[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await listProjects();
      setRows(res.projects);
      setCanEdit(res.can_edit);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load projects.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(body: ProjectInput) {
    setBusy(true);
    setFormError(null);
    try {
      await createProject(body);
      setAdding(false);
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Could not create the project.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Projects &amp; grants</h1>
            <p className="mt-1 text-sm text-gray-500">
              Each grant&apos;s budget, what has been paid, what is on its way, and what is left. Every figure comes from the payments,
              salaries and requests behind it.
            </p>
          </div>
          {canEdit && !adding && (
            <button onClick={() => setAdding(true)}
                    className="inline-flex shrink-0 items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
              <Plus className="h-4 w-4" /> New project
            </button>
          )}
        </div>

        {adding && (
          <div className="mb-8">
            <ProjectForm creating busy={busy} error={formError} onSave={save} onCancel={() => setAdding(false)} />
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading projects…
          </div>
        ) : error ? (
          <p className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-300 py-16 text-center">
            <FolderKanban className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-3 text-sm text-gray-600">No projects yet.</p>
            {canEdit && <p className="mt-1 text-xs text-gray-400">Add your first grant with &ldquo;New project&rdquo;.</p>}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {rows.map((p) => {
              const used = p.paid + p.salary;
              return (
                <Link key={p.agreement_id} href={`/projects/${encodeURIComponent(p.project_code)}`}
                      className="block rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:border-blue-300 hover:shadow">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{p.donor}</div>
                      <div className="mt-0.5 font-semibold text-gray-900">{p.project_code}</div>
                      {p.title && <div className="text-sm text-gray-600">{p.title}</div>}
                    </div>
                    {p.status !== "active" && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{p.status}</span>
                    )}
                  </div>
                  <div className="mt-4">
                    <BudgetBar budget={p.budget} used={used} committed={p.committed} />
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <dt className="text-gray-500">Paid</dt>
                      <dd className="font-medium text-gray-900">{money(used, p.currency)}</dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">On its way</dt>
                      <dd className="font-medium text-gray-900">{money(p.committed, p.currency)}</dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">Left</dt>
                      <dd className={`font-medium ${p.remaining < 0 ? "text-red-600" : "text-gray-900"}`}>
                        {p.budget ? money(p.remaining, p.currency) : "No budget set"}
                      </dd>
                    </div>
                  </dl>
                  {(p.start_date || p.end_date) && (
                    <p className="mt-3 text-xs text-gray-400">
                      {shortDate(p.start_date)} – {shortDate(p.end_date)}
                    </p>
                  )}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
